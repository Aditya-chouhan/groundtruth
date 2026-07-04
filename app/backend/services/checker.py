"""Deterministic checks — every finding is a checkable fact, not an LLM guess.

MVP rule: *auto-close-without-fix* (the real mem0ai/mem0 #6021 pattern found in
the concierge demo). A PR that references an issue with a GitHub closing keyword
but whose diff touches only test files would auto-close the issue without fixing it.
"""
import re
from datetime import datetime, UTC

from sqlalchemy.ext.asyncio import AsyncSession

from models.repository import Repository, RepositoryActivity, WebhookFinding
from services.github_client import GitHubClient

CLOSING_KEYWORD = re.compile(r"\b(?:fix(?:es|ed)?|close[sd]?|resolve[sd]?)\s+#(\d+)", re.IGNORECASE)

_TEST_PATTERNS = (
    re.compile(r"(^|/)tests?/"),
    re.compile(r"(^|/)test_[^/]+$"),
    re.compile(r"_test\.[a-z]+$"),
    re.compile(r"\.test\.[a-z]+$"),
    re.compile(r"\.spec\.[a-z]+$"),
)


def is_test_file(path: str) -> bool:
    return any(p.search(path) for p in _TEST_PATTERNS)


def extract_linked_issue(text: str) -> int | None:
    match = CLOSING_KEYWORD.search(text or "")
    return int(match.group(1)) if match else None


def check_autoclose_without_fix(pr_number: int, title: str, body: str,
                                changed_files: list[dict]) -> dict | None:
    """Pure rule: returns a finding dict, or None if the PR is clean."""
    linked_issue = extract_linked_issue(f"{title or ''} {body or ''}")
    if linked_issue is None or not changed_files:
        return None
    filenames = [f.get("filename", "") for f in changed_files]
    if not all(is_test_file(name) for name in filenames):
        return None
    return {
        "pr_number": pr_number,
        "linked_issue": linked_issue,
        "changed_files": filenames,
        "explanation": (
            f"PR #{pr_number} references issue #{linked_issue} with a closing keyword, "
            f"but every changed file is a test file — merging would auto-close the "
            f"issue without fixing it."
        ),
    }


async def run_checks(
    db: AsyncSession,
    repository: Repository,
    client: GitHubClient,
    activities: list[RepositoryActivity],
) -> list[WebhookFinding]:
    """Run deterministic checks over ingested PRs; persist findings."""
    findings: list[WebhookFinding] = []
    now = datetime.now(UTC).isoformat()

    for activity in activities:
        if activity.activity_type != "pr" or not activity.external_id:
            continue
        pr_number = int(activity.external_id)
        # Only fetch the file list for PRs that even claim to close an issue
        if extract_linked_issue(f"{activity.title or ''} {activity.raw_content or ''}") is None:
            continue
        files = await client.list_pull_request_files(
            repository.owner, repository.name, pr_number
        )
        result = check_autoclose_without_fix(
            pr_number, activity.title or "", activity.raw_content or "", files
        )
        if result:
            findings.append(WebhookFinding(
                workspace_id=repository.workspace_id,
                repository_id=repository.id,
                event_type="pull_request",
                external_id=str(pr_number),
                severity="warning",
                title="PR uses auto-close keyword but only adds tests",
                details=result,
                checked_at=now,
            ))

    db.add_all(findings)
    await db.flush()
    return findings
