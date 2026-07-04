"""
Universal chat endpoint — routes queries to the RepositoryAgent.
"""
import os

import anthropic
import openai
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_db
from agents.repository_agent import RepositoryAgent
from routers.deps import get_current_user

router = APIRouter()

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "anthropic")


def _make_llm_client():
    if LLM_PROVIDER == "deepseek":
        return openai.AsyncOpenAI(
            api_key=os.getenv("DEEPSEEK_API_KEY"),
            base_url="https://api.deepseek.com",
        )
    return anthropic.AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


class ChatRequest(BaseModel):
    query: str
    workspace_id: str


@router.post("/")
async def chat(
    body: ChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: tuple[str, str] = Depends(get_current_user),
):
    _, token_workspace_id = current_user
    if body.workspace_id != token_workspace_id:
        raise HTTPException(status_code=403, detail="Access denied")

    llm_client = _make_llm_client()
    oai = openai.AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    claude_client = None if LLM_PROVIDER == "deepseek" else llm_client
    agent = RepositoryAgent(body.workspace_id, claude_client, oai, db)

    async def generate():
        stream = await agent.run(body.query, stream=True)
        async for chunk in stream:  # type: ignore[union-attr]
            yield f"data: {chunk}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
