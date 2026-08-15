#!/usr/bin/env python3
"""Standalone scan runner — no web app, no Postgres, no Redis.

Calls the real HttpGitHubClient against public GitHub repos, runs the same
pure `check_autoclose_without_fix` rule and `build_claude_md` compiler that
the full app uses, and writes results straight to output/. This exists to
prove the groundtruth loop works on real data before any of the multi-tenant
SaaS scaffolding in docs/product-requirements.md gets built.

Every finding in output/findings.json is a CANDIDATE, not a verified claim.
The false-positive class is real: a PR that only touches test files can
correctly close an issue like "add regression coverage for X". Nothing here
gets published without a human opening the PR and confirming it by hand —
see docs/VERIFICATION.md (written alongside this script) for that pass.

Usage:
    GITHUB_TOKEN=$(gh auth token) .venv/bin/python3 scripts/scan.py
"""
import asyncio
import json
import os
import sys
import types
from datetime import datetime, UTC
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app" / "backend"))

from services.checker import check_autoclose_without_fix, extract_linked_issue  # noqa: E402
from services.compiler import build_claude_md, build_skill_md, _analyze  # noqa: E402
from services.github_client import HttpGitHubClient, default_since  # noqa: E402

# Active, moderate-size public repos across a few ecosystems. Deliberately
# excludes kubernetes/rust/tensorflow-scale monorepos — PR-file fetch volume
# there would burn the rate-limit budget on repos too big to hand-verify
# findings for in one pass anyway.
TARGET_REPOS = [
    ("mem0ai", "mem0"),           # the original precedent (checker.py's docstring)
    ("tiangolo", "fastapi"),
    ("pallets", "flask"),
    ("psf", "requests"),
    ("encode", "httpx"),
    ("pydantic", "pydantic"),
    ("celery", "celery"),
    ("run-llama", "llama_index"),
    ("streamlit", "streamlit"),
    ("gradio-app", "gradio"),
    ("openai", "openai-python"),
    ("anthropics", "anthropic-sdk-python"),
    ("withastro", "astro"),
    ("remix-run", "remix"),
    ("prisma", "prisma"),
    ("expressjs", "express"),
    ("fastify", "fastify"),
    ("nestjs", "nest"),
    ("supabase", "supabase"),
    ("n8n-io", "n8n"),
    ("directus", "directus"),
    ("strapi", "strapi"),
    ("tailwindlabs", "tailwindcss"),
    ("vitejs", "vite"),
    ("sveltejs", "svelte"),
    ("honojs", "hono"),
    ("trpc", "trpc"),
    ("langgenius", "dify"),
    ("crewAIInc", "crewAI"),
    ("BerriAI", "litellm"),
]

CONCURRENCY = 10  # global cap across ALL GitHub calls (repo scans + per-PR file
# fetches together) — a big repo like mem0 can have 300+ closing-keyword PRs in
# a 30-day window, each needing its own files call; without a shared limiter
# those calls run sequentially per-repo and one large repo dominates wall time.


def to_activity(item: dict, kind: str) -> types.SimpleNamespace:
    return types.SimpleNamespace(
        activity_type=kind,
        title=item.get("title"),
        raw_content=item.get("body") or "",
        author=(item.get("user") or {}).get("login"),
        number=item.get("number"),
        html_url=item.get("html_url"),
        state=item.get("state"),
    )


async def fetch_files_for(client: HttpGitHubClient, owner: str, name: str,
                           pr: dict, sem: asyncio.Semaphore) -> tuple[dict, list[dict] | None]:
    async with sem:
        try:
            files = await client.list_pull_request_files(owner, name, pr["number"])
            return pr, files
        except Exception:
            return pr, None


async def scan_repo(client: HttpGitHubClient, owner: str, name: str, sem: asyncio.Semaphore) -> dict:
    try:
        since = default_since(30)
        async with sem:
            repo_meta = await client.get_repo(owner, name)
        async with sem:
            prs = await client.list_pull_requests(owner, name, since)
        async with sem:
            issues = await client.list_issues(owner, name, since)
    except Exception as e:
        return {"owner": owner, "name": name, "error": str(e)}

    activities = [to_activity(p, "pr") for p in prs] + [to_activity(i, "issue") for i in issues]
    stats = _analyze(activities)

    repo_obj = types.SimpleNamespace(
        owner=owner, name=name, branch=repo_meta.get("default_branch", "main")
    )
    compiled_claude_md = build_claude_md(repo_obj, stats)
    compiled_skill_md = build_skill_md(repo_obj, stats)

    # Every closing-keyword PR needs its own files call — fetch them all
    # concurrently (bounded by the shared global semaphore) instead of one
    # at a time; this is what made a 300+-PR repo dominate the dry run.
    keyword_prs = [
        pr for pr in prs
        if extract_linked_issue(f"{pr.get('title') or ''} {pr.get('body') or ''}") is not None
    ]
    fetch_results = await asyncio.gather(*[
        fetch_files_for(client, owner, name, pr, sem) for pr in keyword_prs
    ])

    candidates = []
    for pr, files in fetch_results:
        if files is None:
            continue
        result = check_autoclose_without_fix(
            pr["number"], pr.get("title") or "", pr.get("body") or "", files
        )
        if result:
            result["repo"] = f"{owner}/{name}"
            result["pr_url"] = f"https://github.com/{owner}/{name}/pull/{pr['number']}"
            result["pr_state"] = pr.get("state")
            result["pr_merged_at"] = pr.get("merged_at")
            result["pr_author"] = (pr.get("user") or {}).get("login")
            result["verified"] = None  # filled in by the hand-verification pass
            candidates.append(result)

    print(f"  {owner}/{name}: {len(prs)} PRs, {len(issues)} issues, "
          f"{len(keyword_prs)} PRs with closing keywords, {len(candidates)} candidate findings")

    return {
        "owner": owner,
        "name": name,
        "pr_count": len(prs),
        "issue_count": len(issues),
        "checked_prs": len(keyword_prs),
        "candidates": candidates,
        "compiled_claude_md": compiled_claude_md,
        "compiled_skill_md": compiled_skill_md,
    }


async def main() -> None:
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        print("WARNING: no GITHUB_TOKEN set — rate limit is 60/hr and this scan will likely fail.")
        print("Run: GITHUB_TOKEN=$(gh auth token) .venv/bin/python3 scripts/scan.py")

    client = HttpGitHubClient(token=token)
    sem = asyncio.Semaphore(CONCURRENCY)

    print(f"Scanning {len(TARGET_REPOS)} repos (last 30 days, concurrency={CONCURRENCY})...")
    results = await asyncio.gather(*[
        scan_repo(client, owner, name, sem) for owner, name in TARGET_REPOS
    ])

    out_dir = Path(__file__).resolve().parent.parent / "output"
    (out_dir / "rulebooks").mkdir(parents=True, exist_ok=True)

    all_candidates = []
    repo_summaries = []
    errors = []
    for r in results:
        if "error" in r:
            errors.append(r)
            continue
        repo_summaries.append({k: v for k, v in r.items() if k not in ("candidates", "compiled_claude_md", "compiled_skill_md")})
        all_candidates.extend(r["candidates"])
        slug = f"{r['owner']}-{r['name']}"
        (out_dir / "rulebooks" / f"{slug}-CLAUDE.md").write_text(r["compiled_claude_md"])
        (out_dir / "rulebooks" / f"{slug}-SKILL.md").write_text(r["compiled_skill_md"])

    findings_path = out_dir / "findings.json"
    findings_path.write_text(json.dumps({
        "scanned_at": datetime.now(UTC).isoformat(),
        "repos_scanned": len(repo_summaries),
        "repos_errored": len(errors),
        "errors": errors,
        "repo_summaries": repo_summaries,
        "candidates": all_candidates,
    }, indent=2))

    print(f"\nDone. {len(repo_summaries)} repos scanned, {len(errors)} errored, "
          f"{len(all_candidates)} candidate findings written to {findings_path}")
    print("NEXT STEP: hand-verify every candidate before publishing. "
          "None of these are confirmed yet — see docs/VERIFICATION.md.")


if __name__ == "__main__":
    asyncio.run(main())
