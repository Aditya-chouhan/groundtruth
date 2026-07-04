from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel

from db import get_db
from models.repository import Repository, RuleBook, WebhookFinding
from routers.deps import require_workspace
from services.indexing import run_indexing

router = APIRouter()


class AddRepositoryRequest(BaseModel):
    name: str
    owner: str
    branch: str = "main"


@router.get("/{workspace_id}")
async def list_repositories(
    workspace_id: str = Depends(require_workspace),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Repository).where(
            Repository.workspace_id == workspace_id,
            Repository.status != "deleted",
        )
    )
    repos = result.scalars().all()
    return [
        {
            "id": r.id,
            "name": r.name,
            "owner": r.owner,
            "branch": r.branch,
            "status": r.status,
            "created_at": r.created_at,
        }
        for r in repos
    ]


@router.post("/{workspace_id}")
async def add_repository(
    body: AddRepositoryRequest,
    background_tasks: BackgroundTasks,
    workspace_id: str = Depends(require_workspace),
    db: AsyncSession = Depends(get_db),
):
    repository = Repository(
        workspace_id=workspace_id,
        name=body.name,
        owner=body.owner,
        branch=body.branch,
        status="indexing",
    )
    db.add(repository)
    await db.commit()
    await db.refresh(repository)

    background_tasks.add_task(run_indexing, repository.id)
    return {"id": repository.id, "name": repository.name, "status": "indexing_started"}


@router.delete("/{workspace_id}/{repository_id}")
async def delete_repository(
    repository_id: str,
    workspace_id: str = Depends(require_workspace),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Repository).where(
            Repository.id == repository_id,
            Repository.workspace_id == workspace_id,
        )
    )
    repository = result.scalar_one_or_none()
    if not repository:
        raise HTTPException(status_code=404, detail="Repository not found")
    repository.status = "deleted"
    await db.commit()
    return {"status": "deleted"}


@router.get("/{workspace_id}/{repository_id}/rulebook")
async def get_rulebook(
    repository_id: str,
    workspace_id: str = Depends(require_workspace),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(RuleBook).where(
            RuleBook.workspace_id == workspace_id,
            RuleBook.repository_id == repository_id,
            RuleBook.is_current == True,
        )
    )
    rulebooks = result.scalars().all()
    if not rulebooks:
        raise HTTPException(status_code=404, detail="No rulebook found yet — indexing may still be running")
    return [
        {
            "id": rb.id,
            "filename": rb.filename,
            "content": rb.content,
            "version": rb.version,
            "generated_at": rb.created_at,
        }
        for rb in rulebooks
    ]


@router.post("/{workspace_id}/{repository_id}/rulebook/regenerate")
async def regenerate_rulebook(
    repository_id: str,
    background_tasks: BackgroundTasks,
    workspace_id: str = Depends(require_workspace),
    db: AsyncSession = Depends(get_db),
):
    """Re-index repository and regenerate rulebooks."""
    result = await db.execute(
        select(Repository).where(
            Repository.id == repository_id,
            Repository.workspace_id == workspace_id,
        )
    )
    repository = result.scalar_one_or_none()
    if not repository:
        raise HTTPException(status_code=404, detail="Repository not found")
    repository.status = "indexing"
    await db.commit()

    background_tasks.add_task(run_indexing, repository_id)
    return {"status": "regeneration_started"}


@router.get("/{workspace_id}/{repository_id}/findings")
async def get_findings(
    repository_id: str,
    workspace_id: str = Depends(require_workspace),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(WebhookFinding).where(
            WebhookFinding.workspace_id == workspace_id,
            WebhookFinding.repository_id == repository_id,
        ).order_by(WebhookFinding.created_at.desc())
    )
    findings = result.scalars().all()
    return [
        {
            "id": f.id,
            "event_type": f.event_type,
            "external_id": f.external_id,
            "severity": f.severity,
            "title": f.title,
            "details": f.details,
            "checked_at": f.checked_at,
        }
        for f in findings
    ]


# Indexing pipeline lives in services/indexing.py (ingest → compile → check).
# Mock vs live GitHub is controlled by the GITHUB_MODE env var (see services/github_client.py).
