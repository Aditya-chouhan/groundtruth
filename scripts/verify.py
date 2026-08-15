#!/usr/bin/env python3
"""Fetch real context (linked issue text, PR body, merge state) for every
candidate finding so a human — or an agent reading real text, not just
running the heuristic again — can judge whether each one is genuine.

This does not decide anything. It gathers the evidence a verifier needs:
- Was the PR merged? (an unmerged/closed PR that would have auto-closed
  the issue is a weaker claim than a merged one)
- What does the linked issue actually ask for? If it asks for "add a
  regression test" / "add coverage for X" and the PR does exactly that,
  the PR is NOT a bug — it correctly closes a test-request issue. That is
  the false-positive class named in checker.py's own docstring.
- What does the PR description say it's doing?

Writes output/verification_context.json for review.
"""
import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app" / "backend"))
from services.github_client import HttpGitHubClient  # noqa: E402

CONCURRENCY = 4  # GitHub's secondary abuse-detection triggers on burst
# concurrency well before the primary 5000/hr quota is threatened — this
# runs a small, fixed set of one-off detail fetches, not a bulk scan, so
# there's no throughput reason to push it.
MAX_RETRIES = 4


async def _get_with_retry(client: HttpGitHubClient, path: str, sem: asyncio.Semaphore) -> dict:
    async with sem:
        delay = 2.0
        last_err = None
        for attempt in range(MAX_RETRIES):
            try:
                resp = await client._get(path)
                return resp.json()
            except Exception as e:
                last_err = e
                if "403" not in str(e) and "429" not in str(e):
                    raise
                await asyncio.sleep(delay)
                delay *= 2
        raise last_err


async def fetch_issue(client: HttpGitHubClient, owner: str, name: str, number: int, sem: asyncio.Semaphore) -> dict:
    try:
        issue = await _get_with_retry(client, f"/repos/{owner}/{name}/issues/{number}", sem)
        return {
            "number": number,
            "title": issue.get("title"),
            "body": (issue.get("body") or "")[:1500],
            "state": issue.get("state"),
            "labels": [l.get("name") for l in issue.get("labels", [])],
        }
    except Exception as e:
        return {"number": number, "error": str(e)}


async def fetch_pr(client: HttpGitHubClient, owner: str, name: str, number: int, sem: asyncio.Semaphore) -> dict:
    try:
        pr = await _get_with_retry(client, f"/repos/{owner}/{name}/pulls/{number}", sem)
        return {
            "number": number,
            "title": pr.get("title"),
            "body": (pr.get("body") or "")[:1500],
            "merged": pr.get("merged"),
            "state": pr.get("state"),
            "additions": pr.get("additions"),
            "deletions": pr.get("deletions"),
            "changed_files": pr.get("changed_files"),
        }
    except Exception as e:
        return {"number": number, "error": str(e)}


async def main() -> None:
    findings_path = Path(__file__).resolve().parent.parent / "output" / "findings.json"
    d = json.loads(findings_path.read_text())
    candidates = d["candidates"]

    client = HttpGitHubClient(token=os.getenv("GITHUB_TOKEN"))
    sem = asyncio.Semaphore(CONCURRENCY)

    print(f"Fetching real context for {len(candidates)} candidates...")
    issue_tasks, pr_tasks = [], []
    for c in candidates:
        owner, name = c["repo"].split("/")
        issue_tasks.append(fetch_issue(client, owner, name, c["linked_issue"], sem))
        pr_tasks.append(fetch_pr(client, owner, name, c["pr_number"], sem))

    issues = await asyncio.gather(*issue_tasks)
    prs = await asyncio.gather(*pr_tasks)

    context = []
    for c, issue, pr in zip(candidates, issues, prs):
        context.append({
            "repo": c["repo"],
            "pr_number": c["pr_number"],
            "pr_url": c["pr_url"],
            "linked_issue": c["linked_issue"],
            "changed_files": c["changed_files"],
            "checker_explanation": c["explanation"],
            "issue_context": issue,
            "pr_context": pr,
        })

    out_path = Path(__file__).resolve().parent.parent / "output" / "verification_context.json"
    out_path.write_text(json.dumps(context, indent=2))
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
