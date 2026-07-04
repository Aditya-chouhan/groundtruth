"""
Vector store — semantic retrieval over workspace knowledge.
This is what prevents context bloat: we retrieve only what's relevant, never dump all data.
"""
from typing import Optional
import anthropic
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from models.repository import KnowledgeChunk


EMBEDDING_MODEL = "text-embedding-3-small"  # OpenAI — 1536 dims, cheap


async def embed(text_content: str, openai_client) -> list[float]:
    response = await openai_client.embeddings.create(
        input=text_content,
        model=EMBEDDING_MODEL
    )
    return response.data[0].embedding


async def store_chunk(
    db: AsyncSession,
    workspace_id: str,
    source_type: str,
    content: str,
    openai_client,
    source_id: Optional[str] = None,
    chunk_metadata: Optional[dict] = None,
) -> KnowledgeChunk:
    vector = await embed(content, openai_client)
    chunk = KnowledgeChunk(
        workspace_id=workspace_id,
        source_type=source_type,
        source_id=source_id,
        content=content,
        chunk_metadata=chunk_metadata or {},
        embedding=vector,
    )
    db.add(chunk)
    await db.commit()
    return chunk


async def retrieve(
    db: AsyncSession,
    workspace_id: str,
    query: str,
    openai_client,
    source_type: Optional[str] = None,
    top_k: int = 15,
) -> list[KnowledgeChunk]:
    """Semantic search — returns top_k most relevant chunks for this query."""
    query_vector = await embed(query, openai_client)

    filter_clause = "workspace_id = :workspace_id"
    params = {"workspace_id": workspace_id, "query_vec": str(query_vector), "top_k": top_k}

    if source_type:
        filter_clause += " AND source_type = :source_type"
        params["source_type"] = source_type

    # pgvector cosine similarity search
    sql = text(f"""
        SELECT * FROM knowledge_chunks
        WHERE {filter_clause}
        ORDER BY embedding <=> CAST(:query_vec AS vector)
        LIMIT :top_k
    """)

    result = await db.execute(sql, params)
    rows = result.fetchall()
    return [KnowledgeChunk(**dict(row._mapping)) for row in rows]
