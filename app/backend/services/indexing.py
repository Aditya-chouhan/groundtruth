"""Indexing orchestrator: ingest → compile → check → mark repository active."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from models.repository import Repository
from services.compiler import compile_rulebooks
from services.checker import run_checks
from services.github_client import GitHubClient, get_github_client
from services.ingestion import ingest_repository


async def index_repository(
    db: AsyncSession,
    repository: Repository,
    client: GitHubClient,
    days: int = 30,
) -> Repository:
    """Full pipeline against an open session. Leaves repository status='active'."""
    activities = await ingest_repository(db, repository, client, days=days)
    await compile_rulebooks(db, repository, activities)
    await run_checks(db, repository, client, activities)
    repository.status = "active"
    await db.commit()
    return repository


async def run_indexing(
    repository_id: str,
    session_factory: async_sessionmaker | None = None,
    client: GitHubClient | None = None,
) -> None:
    """Background-task entrypoint: opens its own session, resolves the client, runs the pipeline.

    On failure the repository is marked status='error' rather than left stuck in 'indexing'.
    """
    if session_factory is None:
        from db import AsyncSessionLocal
        session_factory = AsyncSessionLocal
    client = client or get_github_client()

    async with session_factory() as db:
        result = await db.execute(select(Repository).where(Repository.id == repository_id))
        repository = result.scalar_one_or_none()
        if repository is None:
            return
        try:
            await index_repository(db, repository, client)
        except Exception:
            await db.rollback()
            repository.status = "error"
            await db.commit()
            raise
