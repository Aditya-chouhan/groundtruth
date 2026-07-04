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
    "businessbrain",
    broker=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
    backend=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
)

celery_app.conf.beat_schedule = {
    "research-all-competitors-nightly": {
        "task": "tasks.research_all_workspaces",
        "schedule": crontab(hour=2, minute=0),  # 2am daily
    },
}
celery_app.conf.timezone = "UTC"


@celery_app.task(name="tasks.research_all_workspaces")
def research_all_workspaces():
    """Nightly task: re-scrape all active competitors and regenerate battle cards."""
    asyncio.run(_research_all())


async def _research_all():
    from db import AsyncSessionLocal
    from models.workspace import Workspace
    from models.intelligence import Competitor
    from agents.competitive_intel import CompetitiveIntelAgent
    import openai as _openai
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        ws_result = await db.execute(select(Workspace).where(Workspace.is_active == True))
        for workspace in ws_result.scalars():
            comp_result = await db.execute(
                select(Competitor).where(
                    Competitor.workspace_id == workspace.id,
                    Competitor.is_active == True,
                )
            )
            oai = _openai.AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            agent = CompetitiveIntelAgent(workspace.id, None, oai, db)
            for competitor in comp_result.scalars():
                try:
                    await agent.research_competitor(competitor.id)
                    await agent.generate_battle_card(competitor.id)
                    print(f"[tasks] Refreshed {competitor.name} for workspace {workspace.id}")
                except Exception as exc:
                    print(f"[tasks] Error refreshing {competitor.name}: {exc}")
