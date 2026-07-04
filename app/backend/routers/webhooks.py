"""GitHub webhook receiver — the live runtime half of the closed loop.

POST /api/webhooks/github receives pull_request events, verifies the HMAC
signature against GITHUB_WEBHOOK_SECRET, runs the deterministic checker on the
PR, and stores findings. Uses 200 + {"status": "ignored"} for events we don't
act on so GitHub never marks deliveries as failed and disables the hook.
"""
import hashlib
import hmac
import os
from datetime import datetime, UTC

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_db
from models.repository import Repository, WebhookFinding
from services.checker import check_autoclose_without_fix
from services.github_client import GitHubClient, get_github_client

router = APIRouter()

HANDLED_ACTIONS = {"opened", "synchronize"}


def get_client() -> GitHubClient:
    """Dependency so tests can override the GitHub client."""
    return get_github_client()


def verify_signature(raw_body: bytes, signature_header: str | None) -> None:
    """HMAC-SHA256 verification of the webhook payload. Raises on any failure."""
    secret = os.getenv("GITHUB_WEBHOOK_SECRET")
    if not secret:
        # Refuse to process unverifiable webhooks rather than silently trusting them
        raise HTTPException(status_code=503, detail="GITHUB_WEBHOOK_SECRET not configured")
    if not signature_header or not signature_header.startswith("sha256="):
        raise HTTPException(status_code=401, detail="Missing X-Hub-Signature-256 header")
    expected = "sha256=" + hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature_header):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")


@router.post("/github")
async def github_webhook(
    request: Request,
    x_github_event: str | None = Header(default=None),
    x_hub_signature_256: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
    client: GitHubClient = Depends(get_client),
):
    raw_body = await request.body()
    verify_signature(raw_body, x_hub_signature_256)

    if x_github_event != "pull_request":
        return {"status": "ignored", "reason": f"event '{x_github_event}' not handled"}

    payload = await request.json()
    action = payload.get("action")
    if action not in HANDLED_ACTIONS:
        return {"status": "ignored", "reason": f"action '{action}' not handled"}

    repo_info = payload.get("repository") or {}
    owner = ((repo_info.get("owner") or {}).get("login")) or ""
    name = repo_info.get("name") or ""
    pr = payload.get("pull_request") or {}
    pr_number = pr.get("number") or payload.get("number")
    if not (owner and name and pr_number):
        raise HTTPException(status_code=400, detail="Malformed pull_request payload")

    result = await db.execute(
        select(Repository).where(
            Repository.owner == owner,
            Repository.name == name,
            Repository.status != "deleted",
        )
    )
    repository = result.scalar_one_or_none()
    if repository is None:
        return {"status": "ignored", "reason": f"repository {owner}/{name} not connected"}

    # Deterministic check: fetch the PR's changed files, apply the rule
    files = await client.list_pull_request_files(owner, name, int(pr_number))
    finding_details = check_autoclose_without_fix(
        int(pr_number), pr.get("title") or "", pr.get("body") or "", files
    )

    # Findings reflect the PR's *current* state: clear previous findings for
    # this PR (a new push may have fixed the problem), then insert if it persists.
    await db.execute(
        delete(WebhookFinding).where(
            WebhookFinding.repository_id == repository.id,
            WebhookFinding.event_type == "pull_request",
            WebhookFinding.external_id == str(pr_number),
        )
    )

    findings_count = 0
    if finding_details:
        db.add(WebhookFinding(
            workspace_id=repository.workspace_id,
            repository_id=repository.id,
            event_type="pull_request",
            external_id=str(pr_number),
            severity="warning",
            title="PR uses auto-close keyword but only adds tests",
            details=finding_details,
            checked_at=datetime.now(UTC).isoformat(),
        ))
        findings_count = 1

    await db.commit()
    return {
        "status": "processed",
        "repository": f"{owner}/{name}",
        "pr_number": int(pr_number),
        "action": action,
        "findings_count": findings_count,
    }
