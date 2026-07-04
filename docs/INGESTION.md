# Ingestion Pipeline — Technical Outline

> How Groundtruth fetches a connected repository's recent activity, stores it, compiles
> rulebooks from it, and runs deterministic checks. This is the spec for
> `app/backend/services/`.

## Flow

```
POST /api/repositories/{workspace_id}          (router)
  └─ Repository row created, status="indexing"
  └─ BackgroundTasks → run_indexing(repository_id, workspace_id)
        1. INGEST   services/ingestion.py   — fetch last 30 days of PRs + issues
        2. COMPILE  services/compiler.py    — activities → CLAUDE.md + SKILL.md rows
        3. CHECK    services/checker.py     — deterministic PR checks → WebhookFinding rows
        4. Repository.status = "active"
```

## 1. GitHub client (`services/github_client.py`)

Two interchangeable implementations behind one interface (`GitHubClient` protocol):

| Implementation | When used | Auth |
|---|---|---|
| `HttpGitHubClient` | Real repos (public endpoints proven in the mem0 demo) | Optional `GITHUB_TOKEN` env — unauthenticated works for public repos at 60 req/hr |
| `MockGitHubClient` | Tests + `GITHUB_MODE=mock` dev runs | none |

Interface (all async, all return plain dicts shaped like the GitHub REST payloads):

- `get_repo(owner, name)` → repo metadata (default_branch, description, language)
- `list_pull_requests(owner, name, since)` → PRs updated in the window (title, number, body, user, merged_at, state)
- `list_issues(owner, name, since)` → issues (GitHub's issues endpoint includes PRs; filter out entries carrying a `pull_request` key)
- `list_pull_request_files(owner, name, number)` → changed files for one PR (filename, additions, deletions)

Endpoints (same ones used by hand in the mem0 demo):
`GET /repos/{o}/{r}`, `GET /repos/{o}/{r}/pulls?state=all&sort=updated&direction=desc`,
`GET /repos/{o}/{r}/issues?state=all&since=...`, `GET /repos/{o}/{r}/pulls/{n}/files`.

30-day window: computed as `datetime.now(UTC) - timedelta(days=30)`; PR list is
paginated newest-first and cut off client-side at the window boundary.

## 2. Ingestion (`services/ingestion.py`)

`ingest_repository(db, repository, client, days=30)`:

1. Fetch PRs and issues via the client.
2. For each, insert a `RepositoryActivity` row:
   - `activity_type`: `"pr"` or `"issue"`
   - `external_id`: the GitHub number (string)
   - `title`, `author`, `payload` (the raw dict), `raw_content` (body text)
3. Idempotent per run: activities from a previous run of the same repo are replaced
   (delete-then-insert keyed on `repository_id`) so re-indexing doesn't duplicate.
4. Returns the list of activity rows for the compiler.

## 3. Compiler (`services/compiler.py`)

`compile_rulebooks(db, repository, activities)` — MVP is a **deterministic template
compile** (no LLM call yet; the LLM pass slots in behind the same function signature later):

- Aggregates observable facts from activities: contributor counts, PR title
  conventions (e.g. share of titles matching `type(scope): message`), linked-issue
  usage, activity volume.
- Renders `CLAUDE.md` (project rules observed from actual activity) and `SKILL.md`
  (a `pr-autoclose-verification` skill — the exact check from the mem0 demo).
- Marks previous `RuleBook` rows `is_current=False`, inserts the new pair
  `is_current=True`, version bumped by 1.0.

## 4. Deterministic checker (`services/checker.py`)

Design rule (locked in `rfs-gap-analysis.md`): **every finding is a checkable fact,
not an LLM guess.**

MVP check — *auto-close-without-fix* (the real mem0 #6021 pattern):

```
IF pr title/body contains a closing keyword referencing issue #N
   (fixes|closes|resolves #N, case-insensitive)
AND every changed file in the PR is a test file
   (path contains "tests/" or basename starts with "test_" / ends with "_test.py|.test.ts|.spec.ts")
THEN finding(severity="warning",
             title="PR uses auto-close keyword but only adds tests",
             details={pr_number, linked_issue, changed_files})
```

`run_checks(db, repository, client, activities)` runs the rule over ingested PRs,
fetching each candidate PR's file list, and persists `WebhookFinding` rows.
Later, the same function is invoked by the live GitHub webhook on `pull_request` events.

## Testing strategy (`tests/`)

- SQLite in-memory (aiosqlite) — create only the tables under test
  (`workspaces`, `users`, `repositories`, `repository_activities`, `rulebooks`,
  `webhook_findings`); `knowledge_chunks` is excluded because its pgvector column
  is Postgres-only.
- `MockGitHubClient` returns canned data modeled on the real mem0 PRs
  (#6021 "fix(mem0): add test for issue #5915" touching only a test file).
- Tests drive `run_indexing` end-to-end and assert:
  1. status transition `indexing` → `active`
  2. current CLAUDE.md + SKILL.md rulebooks exist with compiled content
  3. the test-only auto-close PR produced a warning finding; a normal PR did not
