import os
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
import anthropic
import openai

from db import get_db
from models.repository import Repository, RuleBook, WebhookFinding
from routers.deps import require_workspace

router = APIRouter()

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "anthropic")


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

    background_tasks.add_task(_run_indexing, repository.id, workspace_id)
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

    background_tasks.add_task(_run_indexing, repository_id, workspace_id)
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


async def _run_indexing(repository_id: str, workspace_id: str):
    """Background task: index repository (fetch issues/PRs/commits) and compile CLAUDE.md/SKILL.md."""
    # This will be implemented in the ingestion/compiler module.
    # For now, it updates repository status to active and inserts a dummy CLAUDE.md
    from db import AsyncSessionLocal
    from models.repository import Repository as RepoModel, RuleBook as RuleBookModel
    from sqlalchemy import select as _select
    import datetime

    async with AsyncSessionLocal() as db:
        repo_result = await db.execute(
            _select(RepoModel).where(RepoModel.id == repository_id)
        )
        repository = repo_result.scalar_one_or_none()
        if not repository:
            return

        # Create dummy CLAUDE.md and SKILL.md
        dummy_claude_content = f"""# CLAUDE.md for {repository.owner}/{repository.name}
        
## Build Commands
- Build project: npm run build
- Lint: npm run lint

## Code Style
- Use TypeScript for frontend
- Follow ESLint configuration
- Keep components small and modular
"""

        dummy_skill_content = f"""# Deploy Skill for {repository.owner}/{repository.name}

## Trigger
- Deploy commit on main branch

## Instructions
1. Run lint and test
2. Build production assets
3. Deploy to hosting provider (Vercel/Railway)
"""

        # Delete old current rulebooks
        old_rulebooks = await db.execute(
            _select(RuleBookModel).where(
                RuleBookModel.repository_id == repository_id,
                RuleBookModel.is_current == True
            )
        )
        for rb in old_rulebooks.scalars():
            rb.is_current = False

        claude_rb = RuleBookModel(
            workspace_id=workspace_id,
            repository_id=repository_id,
            filename="CLAUDE.md",
            content=dummy_claude_content,
            is_current=True,
        )
        skill_rb = RuleBookModel(
            workspace_id=workspace_id,
            repository_id=repository_id,
            filename="SKILL.md",
            content=dummy_skill_content,
            is_current=True,
        )

        db.add(claude_rb)
        db.add(skill_rb)

        # Create a dummy webhook finding to demonstrate functionality
        dummy_finding = WebhookFinding(
            workspace_id=workspace_id,
            repository_id=repository_id,
            event_type="pull_request",
            external_id="6021",
            severity="warning",
            title="PR uses auto-close keyword but only adds tests",
            details={
                "pr_number": 6021,
                "title": "fix(mem0): add test for issue #5915",
                "linked_issue": 5915,
                "explanation": "PR #6021 claims 'Fixes #5915' but the diff only touches test files and no source files in the described module."
            },
            checked_at=str(datetime.datetime.utcnow()),
        )
        db.add(dummy_finding)

        repository.status = "active"
        await db.commit()
