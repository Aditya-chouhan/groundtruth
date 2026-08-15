"""GitHub REST client — one interface, two implementations.

`HttpGitHubClient` hits the same public endpoints used by hand in the mem0 demo
(unauthenticated works for public repos; set GITHUB_TOKEN to raise rate limits).
`MockGitHubClient` returns canned data shaped like real GitHub payloads, modeled
on the actual mem0 PRs — used in tests and GITHUB_MODE=mock dev runs.
"""
import os
from datetime import datetime, timedelta, UTC
from typing import Protocol

import httpx

GITHUB_API = "https://api.github.com"


class GitHubClient(Protocol):
    async def get_repo(self, owner: str, name: str) -> dict: ...

    async def list_pull_requests(self, owner: str, name: str, since: datetime) -> list[dict]: ...

    async def list_issues(self, owner: str, name: str, since: datetime) -> list[dict]: ...

    async def list_pull_request_files(self, owner: str, name: str, number: int) -> list[dict]: ...


def default_since(days: int = 30) -> datetime:
    return datetime.now(UTC) - timedelta(days=days)


class HttpGitHubClient:
    """Lightweight httpx client for public GitHub REST endpoints."""

    def __init__(self, token: str | None = None, timeout: float = 30.0):
        self._token = token or os.getenv("GITHUB_TOKEN")
        self._timeout = timeout

    def _headers(self) -> dict:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    async def _get(self, path: str, params: dict | None = None) -> httpx.Response:
        async with httpx.AsyncClient(timeout=self._timeout, follow_redirects=True) as client:
            resp = await client.get(f"{GITHUB_API}{path}", params=params, headers=self._headers())
            resp.raise_for_status()
            return resp

    async def get_repo(self, owner: str, name: str) -> dict:
        resp = await self._get(f"/repos/{owner}/{name}")
        return resp.json()

    async def list_pull_requests(self, owner: str, name: str, since: datetime) -> list[dict]:
        """PRs updated within the window, newest first, cut off client-side."""
        results: list[dict] = []
        page = 1
        while page <= 5:  # hard cap: 500 PRs is plenty for a 30-day MVP scan
            resp = await self._get(
                f"/repos/{owner}/{name}/pulls",
                params={"state": "all", "sort": "updated", "direction": "desc",
                        "per_page": 100, "page": page},
            )
            batch = resp.json()
            if not batch:
                break
            for pr in batch:
                updated = datetime.fromisoformat(pr["updated_at"].replace("Z", "+00:00"))
                if updated < since:
                    return results
                results.append(pr)
            page += 1
        return results

    async def list_issues(self, owner: str, name: str, since: datetime) -> list[dict]:
        """Issues (not PRs) updated within the window."""
        results: list[dict] = []
        page = 1
        while page <= 5:
            resp = await self._get(
                f"/repos/{owner}/{name}/issues",
                params={"state": "all", "since": since.isoformat(),
                        "per_page": 100, "page": page},
            )
            batch = resp.json()
            if not batch:
                break
            # The issues endpoint returns PRs too; a PR carries a "pull_request" key
            results.extend(item for item in batch if "pull_request" not in item)
            page += 1
        return results

    async def list_pull_request_files(self, owner: str, name: str, number: int) -> list[dict]:
        resp = await self._get(f"/repos/{owner}/{name}/pulls/{number}/files",
                               params={"per_page": 100})
        return resp.json()


class MockGitHubClient:
    """Canned data shaped like real GitHub payloads.

    Defaults model the real mem0 pattern found in the concierge demo:
    PR #6021 "fix(mem0): add test for issue #5915" claims Fixes #5915 but its
    diff only touches a test file — plus one healthy PR that actually fixes code.
    """

    def __init__(self,
                 repo: dict | None = None,
                 pull_requests: list[dict] | None = None,
                 issues: list[dict] | None = None,
                 pr_files: dict[int, list[dict]] | None = None):
        now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.repo = repo or {
            "full_name": "mem0ai/mem0",
            "default_branch": "main",
            "description": "The Memory layer for AI Agents",
            "language": "Python",
        }
        self.pull_requests = pull_requests if pull_requests is not None else [
            {
                "number": 6021,
                "title": "fix(mem0): add test for issue #5915",
                "body": "Fixes #5915",
                "state": "open",
                "merged_at": None,
                "updated_at": now,
                "user": {"login": "contributor-a"},
            },
            {
                "number": 6050,
                "title": "fix(vector-store): reset async factory cache",
                "body": "Fixes #5915 properly by clearing the factory fast path.",
                "state": "open",
                "merged_at": None,
                "updated_at": now,
                "user": {"login": "maintainer-b"},
            },
        ]
        self.issues = issues if issues is not None else [
            {
                "number": 5915,
                "title": "AsyncMemory.reset() bypasses VectorStoreFactory.reset()",
                "body": "Calling reset() on AsyncMemory does not clear the factory fast path.",
                "state": "open",
                "updated_at": now,
                "user": {"login": "reporter-c"},
            },
        ]
        self.pr_files = pr_files if pr_files is not None else {
            6021: [
                {"filename": "tests/test_issue_5915.py", "additions": 7, "deletions": 0},
            ],
            6050: [
                {"filename": "mem0/memory/main.py", "additions": 12, "deletions": 3},
                {"filename": "tests/test_issue_5915.py", "additions": 7, "deletions": 0},
            ],
        }

    async def get_repo(self, owner: str, name: str) -> dict:
        return self.repo

    async def list_pull_requests(self, owner: str, name: str, since: datetime) -> list[dict]:
        return self.pull_requests

    async def list_issues(self, owner: str, name: str, since: datetime) -> list[dict]:
        return self.issues

    async def list_pull_request_files(self, owner: str, name: str, number: int) -> list[dict]:
        return self.pr_files.get(number, [])


def get_github_client() -> GitHubClient:
    """Factory: GITHUB_MODE=mock returns canned data; anything else hits GitHub."""
    if os.getenv("GITHUB_MODE", "live").lower() == "mock":
        return MockGitHubClient()
    return HttpGitHubClient()
