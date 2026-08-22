# Groundtruth

**Deterministic checks over developer activity — every finding a checkable fact, not an LLM guess.**

AI coding agents drift because a repo's rules (`CLAUDE.md`, `SKILL.md`, `AGENTS.md`)
go stale the moment they're written. Groundtruth ingests repository activity — PRs,
issues, commits — compiles those rulebooks from what the codebase actually does, and
runs a webhook runtime that checks new activity against them.

The design rule the whole thing is built on:

> Every finding this system surfaces must be a **checkable, deterministic fact**, not
> a probabilistic LLM guess.

**Write-up (the verification run, with all the numbers):**
https://aditya-chouhan.github.io/groundtruth/

---

## Rule #001, verified against 30 real repositories

A PR can claim to fix a bug and only add a test. If it references an issue with a
closing keyword (`Fixes #N`, `Closes #N`, `Resolves #N`) while its diff touches
*only* test files, merging it silently closes the issue — with the underlying code
never changed.

That rule was run against 30 real, active public repositories. Every candidate was
then **hand-checked against the live GitHub issue and PR** before being called a
finding.

| | |
|---|---|
| Real repos scanned | **30** |
| Raw candidate matches | **43** |
| Verified true positives | **26** (23 distinct issues) |
| Verified false positives | **17** |
| Precision, PR-level | **60.5%** (26/43) |
| Precision, issue-level, deduped | **69.7%** (23/33) |
| True positives that actually merged | **0** |

**The last row is the honest one.** Zero of the 26 got merged — every one was caught
by a human maintainer first. Groundtruth did not catch anything a maintainer missed.
What it shows is that the same judgment, made by hand once per PR, can be made
instantly and consistently by a rule instead.

**60.5% precision is published as-is.** A rule that only ever showed its hits would
prove nothing, so the 17 false positives are on the page with the true positives.

## What this is, and what it is not

- **Is:** a candidate-generation heuristic with a mandatory human verification step.
- **Is not:** an auto-blocking enforcement gate. It does not merge, close, or fail a
  check on its own judgment. Verification is deliberately left to a person.

## Two bugs the real-data run found in the rule itself

Verifying against live repositories didn't just test the rule — it broke it twice, in
ways no synthetic fixture would have:

1. **PR-template boilerplate matched as a real reference.** GitHub's default template
   contains `<!-- e.g. "fixes #123" -->`, and `#123` is a real issue in nearly every
   repo old enough to have one. That alone produced 10 false positives across
   `pydantic/pydantic` and `vitejs/vite`. Fixed by stripping HTML comments before
   matching; confirmed by rescan — all 10 disappeared.
2. **A filename can look like a test and not be one.** Streamlit ships a real product
   feature, its `AppTest` framework, in a file named `app_test.py`. Left as a
   documented, tested limitation rather than a repo-specific patch that would just
   trade one blind spot for another.

## Related research

[arXiv:2601.04886](https://arxiv.org/abs/2601.04886) scanned 23,247 AI-authored PRs
and named "Phantom Changes" — descriptions claiming a change never implemented — as
45.4% of the message-code inconsistencies it found. Same failure mode, at PR-description
granularity rather than repo-artifact granularity. Their own caveat applies here too:
high-inconsistency PRs are 1.7% of their corpus, so this is a real but
**narrow-incidence** problem, not a majority-case one.

## Stack

Next.js 14 + TypeScript + Tailwind (frontend) · Python 3.11 + FastAPI (backend) ·
PostgreSQL + pgvector · Redis + Celery · Claude API with prompt caching.
Multi-tenant by construction — every record carries a `workspace_id`.

```
app/backend/    FastAPI — agents/, routers/, models/, memory/, tools/, tests/
app/frontend/   Next.js app router
docs/           ARCHITECTURE.md, product-requirements.md
docker-compose.yml
```

## Scope

The verification run above is the part of this repo with published, checked numbers.
The product itself is a build in progress, not a deployed service — there is no hosted
instance behind this repo, and no customer has run on it.
