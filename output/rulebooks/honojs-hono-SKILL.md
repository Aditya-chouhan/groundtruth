---
name: pr-autoclose-verification
description: Verify that PRs in honojs/hono using GitHub
  auto-close keywords (Fixes/Closes/Resolves #N) actually change non-test code.
---

# PR auto-close verification

When a pull request references an issue with a closing keyword:

1. Fetch the PR's changed files (`GET /repos/{owner}/{repo}/pulls/{n}/files`).
2. If **every** changed file is a test file (path under `tests/`, or named
   `test_*.py` / `*_test.py` / `*.test.ts` / `*.spec.ts`), flag it:
   merging would auto-close the issue without fixing it.
3. Surface the finding with the PR number, linked issue, and file list —
   a checkable fact, not a judgment call.
