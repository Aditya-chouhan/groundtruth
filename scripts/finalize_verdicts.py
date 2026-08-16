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
    6644: "Issue labeled bug/P1-high/accepted: mem0's agent quick-init path exits 0 without MCP-ready state (JSON envelope missing, MEM0_API_KEY unset). PR only adds a test.",
    6643: "Issue labeled bug/P1-high/accepted: reranker failure fallback mutates the caller's input documents in place, writing rerank_score=0.0 onto them (cohere/huggingface/sentence_transformer/zero_entropy). PR only adds a test.",
    6642: "Issue labeled bug/sdk-python/P1-high/accepted: AWS Bedrock Anthropic Converse parsing crashes when a reasoningContent block precedes the text block — indexes content[0] unconditionally. PR only adds a test.",
    6641: "Issue labeled bug/sdk-python/P1-high/accepted: search(rerank=True) reranks only the already-truncated top-k, so reranking can never surface a result ranked just below the limit. PR only adds a test.",
    6625: 'Issue labeled bug/sdk-python/P1-high/vector-store/accepted: Turbopuffer vector store silently drops every filter operator except gte/lte. PR only adds a test.',
    6618: "Issue labeled bug/P2-medium/sdk-python: LMSTUDIO_BASE_URL env var is ignored because the default URL is baked into config before the env fallback runs. PR only adds a test.",
    6617: "Issue labeled bug/sdk-python/P1-high/accepted: AWS Bedrock tool calls send malformed Converse requests for amazon and cohere models — system prompt and message-block formatting wrong for non-Anthropic providers. PR only adds a test.",
    6616: "Issue labeled bug/sdk-python/P1-high/vector-store/accepted: S3 Vectors search score is hardcoded for cosine distance, so euclidean-metric scores clamp to 0.0 for any distance > 1. PR only adds a test.",
    6615: "Issue labeled bug/sdk-python/P1-high/vector-store/accepted: Redis vector store only handles scalar equality in filters, so operator dicts (gte/lte) and $or are silently ignored. PR only adds a test.",
    6614: "Issue labeled bug/P1-high/vector-store/accepted: UpstashVector.list() ignores its top_k argument — hardcodes top_k=100 internally and never trims results to match the requested count. PR only adds a test.",
    6440: "Issue labeled bug/P1-high/accepted: mem0's agent quick-init path exits 0 without MCP-ready state (JSON envelope missing, MEM0_API_KEY unset) — duplicate PR against the same issue as #6644. PR only adds a test.",
    6439: "Issue labeled bug/sdk-python/P1-high/accepted: AWS Bedrock Anthropic Converse parsing crashes when a reasoningContent block precedes the text block — duplicate PR against the same issue as #6642. PR only adds a test.",
    6408: "Issue labeled bug/P1-high/accepted: reranker failure fallback mutates the caller's input documents in place — duplicate PR against the same issue as #6643. PR only adds a test.",
    6376: 'Real production regression: Codex lifecycle hooks fail on every Windows event, flooding user sessions with errors. PR only adds a test.',
    6360: "Issue labeled bug: HuggingFace embedding client drops api_key on the base_url (TEI/HF Inference Endpoint) path — auth is silently never sent. PR only adds a test.",
    6327: "Issue labeled bug/sdk-python/P1-high/accepted: TS OSS default memory store's filter matcher returns on the first operator in a compound field filter, so e.g. {gte, lte} only ever applies gte. PR only adds a test.",
    6304: "Issue labeled bug/P2-medium: XAILLM forwards its already-built httpx.Client into the http_client_proxies argument, crashing whenever a proxy is configured. PR only adds a test.",
    6247: "Issue labeled bug/sdk-python/P1-high/vector-store/accepted: adding the first memory raises MilvusException on Milvus versions below 2.5. PR only adds a test.",
    6201: "Issue labeled bug/P2-medium: TS OSS Redis vector store builds an invalid RediSearch query string ('' instead of '*') when filters are empty or all-null. PR only adds a test.",
    6198: "Issue labeled bug/P2-medium: the Claude Code mem0 plugin's auto_search:false setting is dead — no hook script reads MEM0_AUTO_SEARCH, so disabling it has no effect and quota keeps burning. PR only adds a test.",
    6197: "Issue labeled bug/P1-high/accepted: OSS default config is internally inconsistent — model=None resolves to gpt-5-mini, which rejects the default temperature=0.1, so every add() silently fails LLM extraction. PR only adds a test.",
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
        if is_tp:
            # A true positive must never fall back to FALSE_POSITIVE_REASONS —
            # that produced a live self-contradiction (badge says "true
            # positive", text says "correctly closes it") for 20/26 findings
            # until this was caught. Missing reasoning is now a hard error,
            # not a silent wrong default.
            if c["pr_number"] not in REASONS:
                raise KeyError(
                    f"PR #{c['pr_number']} ({c['repo']}) is in TRUE_POSITIVES "
                    "but has no entry in REASONS — add one before regenerating."
                )
            reasoning = REASONS[c["pr_number"]]
        else:
            reasoning = FALSE_POSITIVE_REASONS.get(c["repo"], "")
        verdicts.append({
            **c,
            "verdict": "true_positive" if is_tp else "false_positive",
            "reasoning": reasoning,
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
