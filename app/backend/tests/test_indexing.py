"""Tests for the goal's three requirements:

1. Repository registration + status transition indexing → active
2. RuleBook generation (CLAUDE.md and SKILL.md content creation)
3. Finding creation — the deterministic test-only-PR check
"""
import pytest
from sqlalchemy import select

from models.repository import Repository, RepositoryActivity, RuleBook, WebhookFinding
from services.checker import check_autoclose_without_fix, is_test_file
from services.indexing import index_repository, run_indexing


async def _register_repo(db, workspace) -> Repository:
    """Simulate what POST /api/repositories/{workspace_id} does."""
    repo = Repository(
        workspace_id=workspace.id,
        name="mem0",
        owner="mem0ai",
        branch="main",
        status="indexing",
    )
    db.add(repo)
    await db.commit()
    await db.refresh(repo)
    return repo


# ---------------------------------------------------------------- requirement 1

@pytest.mark.asyncio
async def test_registration_starts_in_indexing(db, workspace):
    repo = await _register_repo(db, workspace)
    assert repo.id is not None
    assert repo.status == "indexing"


@pytest.mark.asyncio
async def test_status_transitions_to_active_after_indexing(db, workspace, mock_client):
    repo = await _register_repo(db, workspace)
    await index_repository(db, repo, mock_client)
    await db.refresh(repo)
    assert repo.status == "active"


@pytest.mark.asyncio
async def test_background_entrypoint_runs_full_pipeline(session_factory, db, workspace, mock_client):
    """run_indexing (the BackgroundTasks entrypoint) opens its own session and completes."""
    repo = await _register_repo(db, workspace)
    await run_indexing(repo.id, session_factory=session_factory, client=mock_client)

    async with session_factory() as check_db:
        result = await check_db.execute(select(Repository).where(Repository.id == repo.id))
        assert result.scalar_one().status == "active"


# ---------------------------------------------------------------- requirement 2

@pytest.mark.asyncio
async def test_rulebooks_generated(db, workspace, mock_client):
    repo = await _register_repo(db, workspace)
    await index_repository(db, repo, mock_client)

    result = await db.execute(
        select(RuleBook).where(
            RuleBook.repository_id == repo.id,
            RuleBook.is_current == True,  # noqa: E712
        )
    )
    rulebooks = {rb.filename: rb for rb in result.scalars().all()}

    assert set(rulebooks) == {"CLAUDE.md", "SKILL.md"}
    claude = rulebooks["CLAUDE.md"]
    assert "mem0ai/mem0" in claude.content
    assert "Pull requests: 2" in claude.content          # both mock PRs counted
    assert claude.version == 1.0

    skill = rulebooks["SKILL.md"]
    assert "pr-autoclose-verification" in skill.content
    assert "pulls/{n}/files" in skill.content


@pytest.mark.asyncio
async def test_reindexing_supersedes_previous_rulebooks(db, workspace, mock_client):
    repo = await _register_repo(db, workspace)
    await index_repository(db, repo, mock_client)
    await index_repository(db, repo, mock_client)  # regenerate

    result = await db.execute(select(RuleBook).where(RuleBook.repository_id == repo.id))
    all_rulebooks = list(result.scalars().all())
    current = [rb for rb in all_rulebooks if rb.is_current]
    superseded = [rb for rb in all_rulebooks if not rb.is_current]

    assert len(current) == 2 and len(superseded) == 2
    assert all(rb.version == 2.0 for rb in current)

    # Ingestion is idempotent too — activities were replaced, not duplicated
    result = await db.execute(
        select(RepositoryActivity).where(RepositoryActivity.repository_id == repo.id)
    )
    activities = list(result.scalars().all())
    assert len(activities) == 3  # 2 PRs + 1 issue, once


# ---------------------------------------------------------------- requirement 3

def test_is_test_file():
    assert is_test_file("tests/test_issue_5915.py")
    assert is_test_file("src/module/foo.spec.ts")
    assert is_test_file("pkg/thing_test.go")
    assert not is_test_file("mem0/memory/main.py")
    assert not is_test_file("src/attest/runner.py")  # "test" substring alone doesn't count


def test_check_flags_test_only_autoclose_pr():
    finding = check_autoclose_without_fix(
        6021, "fix(mem0): add test for issue #5915", "Fixes #5915",
        [{"filename": "tests/test_issue_5915.py"}],
    )
    assert finding is not None
    assert finding["pr_number"] == 6021
    assert finding["linked_issue"] == 5915
    assert finding["changed_files"] == ["tests/test_issue_5915.py"]


def test_check_passes_pr_touching_source():
    finding = check_autoclose_without_fix(
        6050, "fix(vector-store): reset async factory cache", "Fixes #5915 properly.",
        [{"filename": "mem0/memory/main.py"}, {"filename": "tests/test_issue_5915.py"}],
    )
    assert finding is None


def test_check_ignores_pr_without_closing_keyword():
    finding = check_autoclose_without_fix(
        7000, "chore: tidy up test helpers", "Refactors helpers, related to #123 but no closing keyword... see issue #123",
        [{"filename": "tests/test_helpers.py"}],
    )
    assert finding is None


@pytest.mark.asyncio
async def test_finding_persisted_for_test_only_pr(db, workspace, mock_client):
    repo = await _register_repo(db, workspace)
    await index_repository(db, repo, mock_client)

    result = await db.execute(
        select(WebhookFinding).where(WebhookFinding.repository_id == repo.id)
    )
    findings = list(result.scalars().all())

    assert len(findings) == 1  # 6021 flagged; 6050 clean
    f = findings[0]
    assert f.external_id == "6021"
    assert f.severity == "warning"
    assert f.event_type == "pull_request"
    assert f.details["linked_issue"] == 5915
    assert f.checked_at
