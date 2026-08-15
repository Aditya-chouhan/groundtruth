#!/usr/bin/env python3
"""Merge the hand-verification judgment calls (made by reading real GitHub
issue/PR data — see output/VERIFIED_FINDINGS.md for the reasoning behind
every one of these) into a single structured file the site generator reads.

The verdicts dict below is not re-derivable from the raw scan — it's the
actual output of a human-in-the-loop review pass across three separate
fetch batches (see session history). Keeping it as an explicit, committed
mapping means the site can never silently regress to "trust the heuristic."
"""
import json
from pathlib import Path

# True positives: real, maintainer-confirmed bug (usually `bug` + `accepted`
# labeled); the PR claims to close it but its diff touches only test files.
TRUE_POSITIVES = {
    # mem0ai/mem0 (22)
    6048, 6644, 6643, 6642, 6641, 6625, 6618, 6617, 6616, 6615, 6614, 6440,
    6439, 6408, 6376, 6360, 6327, 6304, 6247, 6201, 6198, 6197,
    # run-llama/llama_index (3)
    21967, 22576, 22306,
    # fastify/fastify (1)
    6875,
}

REASONS = {
    6048: 'Real TS-side entity-dedup logic bug (unanchored substring check), a regression of an already-fixed Python-side bug (#5630). PR only adds a test.',
    6376: 'Real production regression: Codex lifecycle hooks fail on every Windows event, flooding user sessions with errors. PR only adds a test.',
    21967: "Issue labeled bug/P1: MetadataFilters broken for MultiModalVectorStoreIndex. PR body says 'Adds regression coverage' — never touches the filter logic.",
    22576: 'Issue labeled bug/triage: LanceDB delete predicates built via unescaped string concatenation of doc IDs. PR body confirms it only touches tests/test_index.py.',
    22306: 'Issue labeled bug/triage: ag-ui adapter fabricates a random uuid4() tool_call_id instead of using the real one. PR only adds tests for the (still-wrong) handling.',
    6875: "Real TypeScript .d.ts type-definition bug. PR adds a type-assertion test confirming the wrong type, never touches the actual declaration.",
}

FALSE_POSITIVE_REASONS = {
    'mem0ai/mem0': "Linked issue is itself about test/CI infrastructure (a broken test assertion, a duplicate test file, a CI matrix), not product behavior — a test-only PR correctly closes it.",
    'streamlit/streamlit': "The PR touches lib/streamlit/testing/v1/app_test.py — the implementation of Streamlit's own AppTest product feature, misclassified as a test file by the filename heuristic.",
    'pallets/flask': "Linked issue (#6071) is a pytest-version compatibility break in Flask's own test suite, not a product defect.",
    'expressjs/express': "Linked issue (#7348) is explicitly labeled 'tests' and asks for test coverage of already-working behavior.",
    'run-llama/llama_index': "Linked issue is about llama-dev's own test suite or CI matrix failing, not product behavior.",
}


def main():
    out_dir = Path(__file__).resolve().parent.parent / "output"
    findings = json.loads((out_dir / "findings.json").read_text())

    verdicts = []
    for c in findings["candidates"]:
        is_tp = c["pr_number"] in TRUE_POSITIVES
        verdicts.append({
            **c,
            "verdict": "true_positive" if is_tp else "false_positive",
            "reasoning": REASONS.get(c["pr_number"], FALSE_POSITIVE_REASONS.get(c["repo"], "")),
        })

    tp = [v for v in verdicts if v["verdict"] == "true_positive"]
    fp = [v for v in verdicts if v["verdict"] == "false_positive"]
    tp_merged = [v for v in tp if v.get("pr_state") == "merged" or v.get("pr_merged_at")]

    result = {
        "scanned_at": findings["scanned_at"],
        "repos_scanned": findings["repos_scanned"],
        "total_candidates": len(verdicts),
        "true_positives": len(tp),
        "false_positives": len(fp),
        "true_positives_merged": len(tp_merged),
        "verdicts": verdicts,
    }
    (out_dir / "verified_findings.json").write_text(json.dumps(result, indent=2))
    print(f"{len(tp)} true positives, {len(fp)} false positives, "
          f"{len(tp_merged)} true positives merged (materialized)")
    print(f"Wrote {out_dir / 'verified_findings.json'}")


if __name__ == "__main__":
    main()
