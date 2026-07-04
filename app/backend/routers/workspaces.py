from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from db import get_db
from models.workspace import Workspace
from routers.deps import require_workspace

router = APIRouter()


@router.get("/{workspace_id}")
async def get_workspace(
    workspace_id: str = Depends(require_workspace),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Workspace).where(Workspace.id == workspace_id))
    workspace = result.scalar_one_or_none()
    if not workspace:
        return {"error": "not found"}
    return {"id": workspace.id, "name": workspace.name, "plan": workspace.plan}
