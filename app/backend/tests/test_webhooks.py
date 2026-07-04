"""Webhook receiver tests — signed GitHub pull_request deliveries end to end.

A minimal FastAPI app mounts only the webhooks router with the test DB session
and MockGitHubClient injected; payloads are HMAC-signed exactly as GitHub does.
"""
import hashlib
import hmac
import json

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from db import get_db
from models.repository import Repository, WebhookFinding
from routers import webhooks

SECRET = "test-webhook-secret"


def sign(body: bytes, secret: str = SECRET) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def pr_payload(owner: str, name: str, number: int, title: str, body: str,
               action: str = "opened") -> bytes:
    return json.dumps({
        "action": action,
        "number": number,
        "pull_request": {"number": number, "title": title, "body": body},
        "repository": {"name": name, "full_name": f"{owner}/{name}",
                       "owner": {"login": owner}},
    }).encode()


async def post_webhook(client: AsyncClient, body: bytes,
                       signature: str | None, event: str = "pull_request"):
    headers = {"X-GitHub-Event": event, "Content-Type": "application/json"}
    if signature is not None:
        headers["X-Hub-Signature-256"] = signature
    return await client.post("/api/webhooks/github", content=body, headers=headers)


@pytest_asyncio.fixture
async def connected_repo(db, workspace):
    repo = Repository(workspace_id=workspace.id, name="mem0", owner="mem0ai",
                      branch="main", status="active")
    db.add(repo)
    await db.commit()
    await db.refresh(repo)
    return repo


@pytest_asyncio.fixture
async def http(db, mock_client, monkeypatch):
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", SECRET)

    test_app = FastAPI()
    test_app.include_router(webhooks.router, prefix="/api/webhooks")

    async def override_db():
        yield db

    test_app.dependency_overrides[get_db] = override_db
    test_app.dependency_overrides[webhooks.get_client] = lambda: mock_client

    async with AsyncClient(transport=ASGITransport(app=test_app),
                           base_url="http://test") as client:
        yield client


# ------------------------------------------------------------ signature checks

@pytest.mark.asyncio
async def test_rejects_invalid_signature(http, connected_repo):
    body = pr_payload("mem0ai", "mem0", 6021, "fix: x", "Fixes #5915")
    resp = await post_webhook(http, body, sign(body, "wrong-secret"))
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_rejects_missing_signature(http, connected_repo):
    body = pr_payload("mem0ai", "mem0", 6021, "fix: x", "Fixes #5915")
    resp = await post_webhook(http, body, signature=None)
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_refuses_when_secret_unconfigured(http, connected_repo, monkeypatch):
    monkeypatch.delenv("GITHUB_WEBHOOK_SECRET", raising=False)
    body = pr_payload("mem0ai", "mem0", 6021, "fix: x", "Fixes #5915")
    resp = await post_webhook(http, body, sign(body))
    assert resp.status_code == 503


# ------------------------------------------------------------- event filtering

@pytest.mark.asyncio
async def test_ignores_non_pull_request_events(http, connected_repo):
    body = json.dumps({"zen": "Keep it logically awesome."}).encode()
    resp = await post_webhook(http, body, sign(body), event="ping")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ignored"


@pytest.mark.asyncio
async def test_ignores_unhandled_actions(http, connected_repo):
    body = pr_payload("mem0ai", "mem0", 6021, "fix: x", "Fixes #5915", action="closed")
    resp = await post_webhook(http, body, sign(body))
    assert resp.status_code == 200
    assert resp.json()["status"] == "ignored"


@pytest.mark.asyncio
async def test_ignores_unconnected_repository(http):
    body = pr_payload("someoneelse", "otherrepo", 1, "fix: y", "Fixes #2")
    resp = await post_webhook(http, body, sign(body))
    assert resp.status_code == 200
    assert "not connected" in resp.json()["reason"]


# --------------------------------------------------------- finding persistence

@pytest.mark.asyncio
async def test_flags_test_only_autoclose_pr(http, db, connected_repo):
    """PR #6021: claims Fixes #5915, mock file list is test-only → warning stored."""
    body = pr_payload("mem0ai", "mem0", 6021,
                      "fix(mem0): add test for issue #5915", "Fixes #5915")
    resp = await post_webhook(http, body, sign(body))

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "processed"
    assert data["findings_count"] == 1

    result = await db.execute(
        select(WebhookFinding).where(WebhookFinding.repository_id == connected_repo.id)
    )
    findings = list(result.scalars().all())
    assert len(findings) == 1
    f = findings[0]
    assert f.external_id == "6021"
    assert f.severity == "warning"
    assert f.details["linked_issue"] == 5915
    assert f.details["changed_files"] == ["tests/test_issue_5915.py"]


@pytest.mark.asyncio
async def test_healthy_pr_stores_no_finding(http, db, connected_repo):
    """PR #6050 touches source code → no finding."""
    body = pr_payload("mem0ai", "mem0", 6050,
                      "fix(vector-store): reset async factory cache", "Fixes #5915 properly.")
    resp = await post_webhook(http, body, sign(body))

    assert resp.status_code == 200
    assert resp.json()["findings_count"] == 0

    result = await db.execute(
        select(WebhookFinding).where(WebhookFinding.repository_id == connected_repo.id)
    )
    assert list(result.scalars().all()) == []


@pytest.mark.asyncio
async def test_synchronize_clears_stale_finding(http, db, connected_repo, mock_client):
    """A PR flagged on open, then fixed by a new push, loses its finding on synchronize."""
    body = pr_payload("mem0ai", "mem0", 6021,
                      "fix(mem0): add test for issue #5915", "Fixes #5915")
    resp = await post_webhook(http, body, sign(body))
    assert resp.json()["findings_count"] == 1

    # New push adds the real fix: PR #6021's file list now touches source code
    mock_client.pr_files[6021] = [
        {"filename": "mem0/memory/main.py", "additions": 12, "deletions": 3},
        {"filename": "tests/test_issue_5915.py", "additions": 7, "deletions": 0},
    ]
    body = pr_payload("mem0ai", "mem0", 6021,
                      "fix(mem0): add test for issue #5915", "Fixes #5915",
                      action="synchronize")
    resp = await post_webhook(http, body, sign(body))
    assert resp.json()["findings_count"] == 0

    result = await db.execute(
        select(WebhookFinding).where(WebhookFinding.repository_id == connected_repo.id)
    )
    assert list(result.scalars().all()) == []


# ----------------------------------------------------------------- registration

def test_webhook_route_registered_in_main_app():
    import main
    assert "/api/webhooks/github" in [route.path for route in main.app.routes]
