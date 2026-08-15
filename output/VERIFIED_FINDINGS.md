# Verified findings — auto-close-without-fix scan

Scanned 30 real public repositories (last 30 days of PR activity, Aug 2026) with
`scripts/scan.py` against the live GitHub REST API — no synthetic data, no
seeded fixtures. The rule: does a PR reference an issue with a GitHub closing
keyword (`Fixes #N`, `Closes #N`, `Resolves #N`) while its diff touches only
test files? If merged, that would auto-close the issue without actually
fixing it.

**Every one of the 43 raw candidates below was individually opened against
real GitHub API data — the actual issue body, labels, and PR merge state —
and hand-classified.** None are published as findings without that check;
several categories below exist *because* of it.

## Headline numbers

| | Count |
|---|---|
| Repos scanned | 30 |
| Candidate matches (raw heuristic) | 43 |
| **True positives** (real, maintainer-labeled bug; PR only adds/touches tests) | **26** |
| False positives | 17 |
| True positives that actually **merged** (materialized harm) | **0** |
| False positives that merged (correctly — legitimate test-only closes) | 2 |

The most important honest number in this dataset is the zero. In every
scanned repo, every PR that would have auto-closed a real bug with a
test-only diff was **caught and rejected by human review before merge**.
The tool didn't catch anything a maintainer missed. What it demonstrates is
that the same judgment call — "does this diff actually fix the thing it
claims to fix?" — was made by hand, once per PR, by a maintainer, when it
could have been answered instantly and consistently by a rule.

## Two bugs found in the checker itself while verifying

Verification wasn't just about the target repos — it caught real defects in
groundtruth's own rule, both fixed in `app/backend/services/checker.py`
(regression-tested in `app/backend/tests/test_checker.py`):

1. **PR-template boilerplate matched as a real reference.** GitHub's default
   PR template includes example text like `<!-- e.g. "fixes #123" -->`. The
   original regex matched that literal example just like a real reference —
   and #123 is a real (usually unrelated) issue in nearly every repo old
   enough to have one. This alone produced **10 false positives** across
   `pydantic/pydantic` (2) and `vitejs/vite` (3), plus `crewAIInc/crewAI` (4)
   and `langgenius/dify` (1) in the first pass. Fixed by stripping HTML
   comments before matching. Confirmed fix: those 10 disappeared on rescan.
2. **A filename can look like a test and not be one.** Streamlit ships an
   actual product feature — its `AppTest` testing framework — implemented in
   a file literally named `app_test.py`. The filename heuristic can't tell
   that apart from a real test file. Documented as a known limitation (see
   `test_is_test_file_can_misclassify_a_named_product_module` in the test
   suite) rather than papered over — a repo-specific exception would just
   trade one blind spot for another.
3. **`HttpGitHubClient` didn't follow redirects.** `tiangolo/fastapi`
   redirects to a canonical repo ID; the client raised instead of following
   it, and one full repo scan silently dropped out. Fixed with
   `follow_redirects=True`.

## By repository

### mem0ai/mem0 — 28 candidates → 22 true positives, 6 false positives

The dominant case in the dataset, and the most interesting one. 17 of the 28
PRs share one author (`jaythehardcoder`); every PR is `closed` or `open`,
**none merged**.

**6 false positives** — the linked issue is itself about test/CI
infrastructure, not product behavior, so a test-only PR correctly closes it:
`#6727` (Windows test hardcodes a POSIX module name), `#6687` (merged — Redis
test's own skip-check was broken), `#6943`/`#6234` (duplicate PRs for the
same "cleanup a duplicate test file" chore), `#6332` (a TS test-contract
request), `#6832` (Windows path escaping breaks the test runner, not the
product).

**22 true positives** — the linked issue carries GitHub's `bug` label, often
`P1-high` and `accepted` (maintainer-triaged and confirmed real), with a
concrete, specific defect description — and the PR that claims to close it
touches only test files. A sample, verified against the actual issue text:

- `#6616` → issue: *"S3 Vectors search score is hardcoded for cosine, breaks
  euclidean ranking"* (bug, P1-high, accepted, vector-store) — PR only adds a
  test.
- `#6625` → issue: *"Turbopuffer vector store silently drops filter operators
  other than gte/lte"* (bug, P1-high, accepted) — PR only adds a test.
- `#6197` → issue: *"OSS default config silently breaks add(): model=None
  resolves to gpt-5-mini"* (bug, P1-high, accepted) — PR only adds a test.
- `#6048` → issue: *"Graph entity dedup (TS): distinct entities sharing a
  substring prefix are dropped"* — a real unanchored-substring logic bug
  (`other.includes(entity.text.toLowerCase())`), confirmed as a TS-side
  regression of an already-fixed Python bug (#5630) — PR only adds a test.
- `#6376` → issue: *"Codex lifecycle hooks still fail on v0.2.12 — POSIX
  commands exit 1 on every event"* — a real production regression flooding
  users' sessions with errors, not a test problem — PR only adds a test.

Full list of the 22: `#6048 #6644 #6643 #6642 #6641 #6625 #6618 #6617 #6616
#6615 #6614 #6440 #6439 #6408 #6376 #6360 #6327 #6304 #6247 #6201 #6198
#6197`.

### run-llama/llama_index — 5 candidates → 3 true positives, 2 false positives

- **True positive** `#21967` → issue `#15165`, labeled `bug, P1,
  topic:multimodality`: *"MetadataFilters not working with
  MultiModalVectorStoreIndex"*. PR body literally says "Adds regression
  coverage" and "Closes #15165" — adds a test, never touches the filter
  logic.
- **True positive** `#22576` → issue `#22543`, labeled `bug, triage`: managed
  LanceDB's delete method builds filter predicates via unescaped string
  concatenation of document IDs — an injection-shaped defect. PR's own body:
  *"What changed: tests/test_index.py... Verification: existing suite run
  before/after, no new failures"* — i.e., it explicitly did not touch the
  vulnerable code path.
- **True positive** `#22306` → issue `#22068`, labeled `bug, triage`: an
  ag-ui adapter fabricates a random `uuid4()` when a real `tool_call_id` is
  missing — silently wrong behavior. PR only adds tests for the handling.
- **False positive** `#22696` → issue `#22695`: the llama-dev *test suite
  itself* fails locally due to invalid mocked paths — a test-infra issue, and
  the PR fixes exactly that.
- **False positive** `#21608` → issue `#21607`, labeled `stale`: CI's own
  integration-test matrix is red on main — again, a test/CI-infrastructure
  issue, not product behavior.

### pallets/flask — 5 candidates → 0 true positives, 5 false positives

All five reference the same issue, `#6071`: *"Tests fail with pytest 9.1:
_pytest.monkeypatch.notset removed"* — a pytest version-compatibility
problem in Flask's own test suite, not a product defect. Five different
contributors raced to fix the same trivial issue (three PRs are literally
titled "AI junk" — visibly low-effort submissions); one (`#6095`) merged
legitimately, the other four were correctly closed as duplicates.

### expressjs/express — 2 candidates → 0 true positives, 2 false positives

Both reference issue `#7348`, labeled `tests`: *"Missing test coverage for
req.is() with an array argument."* The issue explicitly asks for test
coverage of already-working behavior — a textbook case of the false-positive
class the checker's own docstring names. Neither PR merged (duplicates).

### fastify/fastify — 1 candidate → 1 true positive

`#6875` → issue `#6836`: *"`LogController.requestCompleted` .d.ts `error`
type inaccurate"* — a real TypeScript type-definition bug. The PR only adds
a `.tst.ts` type-assertion test confirming the (currently wrong) type, and
never touches the actual `.d.ts` declaration. Open, unmerged.

### streamlit/streamlit — 2 candidates → 0 true positives, 2 false positives

Both PRs touch `lib/streamlit/testing/v1/app_test.py` — which the filename
heuristic flags as a test file, but is actually the implementation of
Streamlit's own `AppTest` product feature (see "bugs found in the checker
itself," above). Documented limitation, not a real finding.

## What this dataset actually supports as a claim

Fair: *"Scanned 30 real, active public repositories; found 26 real instances
of a PR claiming to fix a maintainer-confirmed bug while its diff touched
only test files — all 26 were independently caught and rejected by human
review before merge, at the cost of one-by-one manual triage each time."*

Not fair, and not claimed anywhere in this dataset: that any of these repos
shipped a silent auto-close, that mem0 (or anyone else) has a quality
problem, or that `jaythehardcoder`'s contributions were made in bad faith —
the pattern (test-only "fix" PRs against accepted bugs) is consistent with
low-effort or AI-assisted contribution farming, but intent isn't something
this data can establish and this report doesn't claim it.
