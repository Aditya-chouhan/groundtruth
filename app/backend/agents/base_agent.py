"""
Base agent class. All domain agents inherit from this.
Enforces the retrieve → reason → store pattern that prevents context bloat.
"""
import os
from abc import ABC, abstractmethod
from typing import AsyncIterator, Optional

import anthropic
import openai as openai_module
from sqlalchemy.ext.asyncio import AsyncSession

from memory import vector_store

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "anthropic")


class BaseAgent(ABC):
    """
    Every domain agent follows the same loop:
    1. Retrieve relevant context from vector store (bounded, not full DB)
    2. Reason using the configured LLM (DeepSeek for testing, Claude for production)
    3. Store new learnings back to memory

    Max context per call: 20 chunks. Never exceeded.
    """

    MODEL_ANTHROPIC = "claude-sonnet-4-6"
    MODEL_DEEPSEEK = "deepseek-chat"
    MAX_CHUNKS = 20

    def __init__(self, workspace_id: str, claude_client, openai_client, db: AsyncSession):
        self.workspace_id = workspace_id
        self.claude = claude_client
        self.openai = openai_client  # used for embeddings only
        self.db = db
        self._provider = LLM_PROVIDER

        if self._provider == "deepseek":
            self._deepseek = openai_module.AsyncOpenAI(
                api_key=os.getenv("DEEPSEEK_API_KEY"),
                base_url="https://api.deepseek.com",
            )

    @property
    @abstractmethod
    def system_prompt(self) -> str:
        """Domain-specific system prompt."""
        ...

    @property
    @abstractmethod
    def source_type(self) -> str:
        """Which knowledge chunks to search. e.g. 'competitor', 'finance', 'marketing'"""
        ...

    async def run(self, query: str, stream: bool = False) -> str | AsyncIterator:
        # 1. Retrieve — bounded to MAX_CHUNKS; graceful fallback if no embeddings key
        try:
            chunks = await vector_store.retrieve(
                self.db, self.workspace_id, query, self.openai,
                source_type=self.source_type, top_k=self.MAX_CHUNKS
            )
        except Exception:
            chunks = []

        context = self._format_context(chunks)
        messages = [{"role": "user", "content": f"Context:\n{context}\n\nQuery: {query}"}]

        if stream:
            return self._stream(messages)

        # 2. Reason
        if self._provider == "deepseek":
            response = await self._deepseek.chat.completions.create(
                model=self.MODEL_DEEPSEEK,
                max_tokens=4096,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    *messages,
                ],
            )
            result = response.choices[0].message.content
        else:
            response = await self.claude.messages.create(
                model=self.MODEL_ANTHROPIC,
                max_tokens=4096,
                system=[
                    {
                        "type": "text",
                        "text": self.system_prompt,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=messages,
            )
            result = response.content[0].text

        # 3. Store new learnings if agent produced insights worth keeping
        await self._store_learnings(query, result)
        return result

    async def _stream(self, messages: list) -> AsyncIterator:
        if self._provider == "deepseek":
            stream = await self._deepseek.chat.completions.create(
                model=self.MODEL_DEEPSEEK,
                max_tokens=4096,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    *messages,
                ],
                stream=True,
            )
            async for chunk in stream:
                delta = chunk.choices[0].delta.content
                if delta:
                    yield delta
        else:
            async with self.claude.messages.stream(
                model=self.MODEL_ANTHROPIC,
                max_tokens=4096,
                system=[
                    {
                        "type": "text",
                        "text": self.system_prompt,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=messages,
            ) as stream:
                async for text in stream.text_stream:
                    yield text

    def _format_context(self, chunks) -> str:
        if not chunks:
            return "No relevant context found in knowledge base."
        parts = []
        for i, chunk in enumerate(chunks, 1):
            parts.append(f"[{i}] ({chunk.source_type}) {chunk.content}")
        return "\n\n".join(parts)

    async def _store_learnings(self, query: str, response: str):
        """Override in subclass if the agent produces storable insights."""
        pass
