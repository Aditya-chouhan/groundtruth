"""Test fixtures: in-memory SQLite (async) + mock GitHub client.

`knowledge_chunks` is excluded from table creation — its pgvector column is
Postgres-only and nothing under test touches it.
"""
import sys
from pathlib import Path

# Backend modules use top-level imports (`from db import ...`), so the backend
# directory itself must be on sys.path when pytest runs from anywhere.
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool

from models.base import Base
from models.workspace import Workspace, User  # noqa: F401 — registers tables
from models.repository import (  # noqa: F401 — registers tables
    Repository, RepositoryActivity, RuleBook, WebhookFinding, KnowledgeChunk,
)
from services.github_client import MockGitHubClient

TEST_TABLES = [
    Workspace.__table__,
    User.__table__,
    Repository.__table__,
    RepositoryActivity.__table__,
    RuleBook.__table__,
    WebhookFinding.__table__,
]


@pytest_asyncio.fixture
async def session_factory():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(lambda sync_conn: Base.metadata.create_all(sync_conn, tables=TEST_TABLES))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest_asyncio.fixture
async def db(session_factory):
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def workspace(db):
    ws = Workspace(name="Test Workspace", domain="test.dev")
    db.add(ws)
    await db.commit()
    await db.refresh(ws)
    return ws


@pytest.fixture
def mock_client():
    """Canned mem0-style data: PR #6021 (test-only, claims Fixes #5915) + PR #6050 (real fix)."""
    return MockGitHubClient()
