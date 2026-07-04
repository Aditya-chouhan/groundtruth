"""
Celery tasks — scheduled background jobs.
Worker: celery -A tasks worker --beat --loglevel=info
"""
import asyncio
import os

from celery import Celery
from celery.schedules import crontab
from dotenv import load_dotenv

load_dotenv()

celery_app = Celery(
    "groundtruth",
    broker=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
    backend=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
)

celery_app.conf.beat_schedule = {
    # Nightly recompile keeps every active repo's rulebooks current with the
    # last 30 days of activity — the "keeps it current" half of the product.
    "reindex-all-repositories-nightly": {
        "task": "tasks.reindex_all_repositories",
        "schedule": crontab(hour=2, minute=0),  # 2am UTC daily
    },
}
celery_app.conf.timezone = "UTC"


@celery_app.task(name="tasks.reindex_all_repositories")
def reindex_all_repositories():
    """Nightly: re-ingest, recompile rulebooks, and re-run checks for every active repo."""
    asyncio.run(_reindex_all())


async def _reindex_all():
    from db import AsyncSessionLocal
    from models.repository import Repository
    from services.indexing import run_indexing
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Repository).where(Repository.status == "active"))
        repository_ids = [r.id for r in result.scalars()]

    for repository_id in repository_ids:
        try:
            await run_indexing(repository_id)
            print(f"[tasks] Reindexed repository {repository_id}")
        except Exception as exc:
            print(f"[tasks] Error reindexing {repository_id}: {exc}")
