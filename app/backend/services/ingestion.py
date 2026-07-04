"""Ingestion — fetch a repository's recent activity and store it as RepositoryActivity rows."""
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.repository import Repository, RepositoryActivity
from services.github_client import GitHubClient, default_since


async def ingest_repository(
    db: AsyncSession,
    repository: Repository,
    client: GitHubClient,
    days: int = 30,
) -> list[RepositoryActivity]:
    """Fetch last `days` of PRs and issues; replace this repo's stored activities."""
    since = default_since(days)
    prs = await client.list_pull_requests(repository.owner, repository.name, since)
    issues = await client.list_issues(repository.owner, repository.name, since)

    # Idempotent re-index: replace previous activities for this repository
    await db.execute(
        delete(RepositoryActivity).where(RepositoryActivity.repository_id == repository.id)
    )

    activities: list[RepositoryActivity] = []
    for pr in prs:
        activities.append(RepositoryActivity(
            repository_id=repository.id,
            workspace_id=repository.workspace_id,
            activity_type="pr",
            external_id=str(pr.get("number", "")),
            title=(pr.get("title") or "")[:500],
            author=(pr.get("user") or {}).get("login", ""),
            payload=pr,
            raw_content=pr.get("body") or "",
        ))
    for issue in issues:
        activities.append(RepositoryActivity(
            repository_id=repository.id,
            workspace_id=repository.workspace_id,
            activity_type="issue",
            external_id=str(issue.get("number", "")),
            title=(issue.get("title") or "")[:500],
            author=(issue.get("user") or {}).get("login", ""),
            payload=issue,
            raw_content=issue.get("body") or "",
        ))

    db.add_all(activities)
    await db.flush()
    return activities


async def get_activities(db: AsyncSession, repository_id: str) -> list[RepositoryActivity]:
    result = await db.execute(
        select(RepositoryActivity).where(RepositoryActivity.repository_id == repository_id)
    )
    return list(result.scalars().all())
