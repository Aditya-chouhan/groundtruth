"""Compiler — turn ingested activity into executable rulebooks (CLAUDE.md / SKILL.md).

MVP is a deterministic template compile: every statement in the output is an
observable fact aggregated from the activity rows (counts, naming conventions,
linked-issue usage). An LLM synthesis pass can later slot in behind the same
function signature without changing callers.
"""
import re
from collections import Counter

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.repository import Repository, RepositoryActivity, RuleBook

CONVENTIONAL_TITLE = re.compile(r"^(feat|fix|docs|style|refactor|perf|test|build|ci|chore)(\([\w\-./]+\))?!?:\s")
CLOSING_KEYWORD = re.compile(r"\b(fix(?:es|ed)?|close[sd]?|resolve[sd]?)\s+#\d+", re.IGNORECASE)


def _analyze(activities: list[RepositoryActivity]) -> dict:
    prs = [a for a in activities if a.activity_type == "pr"]
    issues = [a for a in activities if a.activity_type == "issue"]
    conventional = [p for p in prs if CONVENTIONAL_TITLE.match(p.title or "")]
    linked = [p for p in prs if CLOSING_KEYWORD.search(f"{p.title or ''} {p.raw_content or ''}")]
    authors = Counter(a.author for a in activities if a.author)
    return {
        "pr_count": len(prs),
        "issue_count": len(issues),
        "conventional_count": len(conventional),
        "linked_count": len(linked),
        "top_authors": authors.most_common(5),
    }


def build_claude_md(repository: Repository, stats: dict) -> str:
    uses_conventional = stats["pr_count"] > 0 and stats["conventional_count"] / stats["pr_count"] >= 0.5
    lines = [
        f"# CLAUDE.md — {repository.owner}/{repository.name}",
        "",
        "> Compiled by Groundtruth from the last 30 days of repository activity.",
        "> Every rule below is an observed fact, not a guess.",
        "",
        "## Observed activity (30 days)",
        f"- Pull requests: {stats['pr_count']}",
        f"- Issues: {stats['issue_count']}",
        f"- Active contributors: {len(stats['top_authors'])}",
        "",
        "## PR conventions (observed)",
    ]
    if uses_conventional:
        lines.append(
            f"- Conventional-commit titles are the norm here "
            f"({stats['conventional_count']}/{stats['pr_count']} recent PRs match "
            f"`type(scope): message`). Follow it."
        )
    else:
        lines.append("- No dominant PR title convention detected; match the style of recent merged PRs.")
    if stats["linked_count"]:
        lines.append(
            f"- {stats['linked_count']}/{stats['pr_count']} recent PRs use GitHub closing keywords "
            f"(`Fixes #N`). Only use a closing keyword when the diff actually resolves the issue "
            f"— see SKILL.md: pr-autoclose-verification."
        )
    lines += [
        "",
        "## Default branch",
        f"- `{repository.branch}`",
        "",
    ]
    return "\n".join(lines)


def build_skill_md(repository: Repository, stats: dict) -> str:
    return "\n".join([
        "---",
        "name: pr-autoclose-verification",
        f"description: Verify that PRs in {repository.owner}/{repository.name} using GitHub",
        "  auto-close keywords (Fixes/Closes/Resolves #N) actually change non-test code.",
        "---",
        "",
        "# PR auto-close verification",
        "",
        "When a pull request references an issue with a closing keyword:",
        "",
        "1. Fetch the PR's changed files (`GET /repos/{owner}/{repo}/pulls/{n}/files`).",
        "2. If **every** changed file is a test file (path under `tests/`, or named",
        "   `test_*.py` / `*_test.py` / `*.test.ts` / `*.spec.ts`), flag it:",
        "   merging would auto-close the issue without fixing it.",
        "3. Surface the finding with the PR number, linked issue, and file list —",
        "   a checkable fact, not a judgment call.",
        "",
    ])


async def compile_rulebooks(
    db: AsyncSession,
    repository: Repository,
    activities: list[RepositoryActivity],
) -> list[RuleBook]:
    """Compile CLAUDE.md + SKILL.md; supersede previous current rulebooks."""
    stats = _analyze(activities)

    result = await db.execute(
        select(RuleBook).where(
            RuleBook.repository_id == repository.id,
            RuleBook.is_current == True,  # noqa: E712
        )
    )
    old = list(result.scalars().all())
    next_version = max((rb.version for rb in old), default=0.0) + 1.0
    for rb in old:
        rb.is_current = False

    new_rulebooks = [
        RuleBook(
            workspace_id=repository.workspace_id,
            repository_id=repository.id,
            filename="CLAUDE.md",
            content=build_claude_md(repository, stats),
            version=next_version,
            is_current=True,
        ),
        RuleBook(
            workspace_id=repository.workspace_id,
            repository_id=repository.id,
            filename="SKILL.md",
            content=build_skill_md(repository, stats),
            version=next_version,
            is_current=True,
        ),
    ]
    db.add_all(new_rulebooks)
    await db.flush()
    return new_rulebooks
