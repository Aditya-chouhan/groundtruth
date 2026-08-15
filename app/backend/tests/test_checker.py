"""Unit tests for the pure checker functions — no DB, no session.

Regression coverage for two false-positive classes found empirically by
scanning 30 real public repos (scripts/scan.py, Aug 2026):

1. PR-template boilerplate (`<!-- e.g. "fixes #123" -->`) was matching the
   closing-keyword regex just like a real reference — and #123 is a real
   issue in nearly every repo old enough to have one, so every PR left with
   the template's example text intact produced a false positive. Confirmed
   live on pydantic/pydantic#13580 and vitejs/vite#23231/#23209/#22972 —
   four unrelated PRs across two repos, all false-matching the same #123.

2. A file can be named like a test (`app_test.py`) while being real product
   source, not a test — confirmed on streamlit/streamlit's own `AppTest`
   feature module (`lib/streamlit/testing/v1/app_test.py`). This is a known,
   *undocumented-as-fixed* limitation of filename-only classification: it
   can't be resolved generically without repo-specific tuning, so it's
   pinned here as a documented false positive, not silently "fixed."
"""
from services.checker import check_autoclose_without_fix, extract_linked_issue, is_test_file


def test_extract_linked_issue_finds_real_reference():
    assert extract_linked_issue("Fixes #5915") == 5915
    assert extract_linked_issue("This closes #42 for good") == 42


def test_extract_linked_issue_ignores_html_comment_boilerplate():
    """The literal false positive found on pydantic/pydantic#13580."""
    body = (
        "## Related issue number\n"
        '<!-- WARNING: please use "fix #123" style references so the issue '
        "is closed when this PR is merged. -->\n"
        "## Checklist"
    )
    assert extract_linked_issue(body) is None


def test_extract_linked_issue_ignores_multiline_template_comment():
    """The literal false positive found on vitejs/vite#23209 and #22972."""
    body = (
        "<!--\n"
        "- What is this PR solving? Write a clear and concise description.\n"
        "- Reference the issues it solves (e.g. `fixes #123`).\n"
        "-->\n"
    )
    assert extract_linked_issue(body) is None


def test_extract_linked_issue_still_finds_real_reference_next_to_a_comment():
    """Stripping comments must not eat real references that sit outside one."""
    body = (
        "<!-- Reference the issues it solves (e.g. `fixes #123`). -->\n"
        "Fixes #4821"
    )
    assert extract_linked_issue(body) == 4821


def test_is_test_file_can_misclassify_a_named_product_module():
    """Documented limitation, not a bug fix: streamlit/streamlit's own
    AppTest feature lives at this exact path and is product code, not a
    test — but the filename convention this repo uses for a REAL testing
    feature is indistinguishable, by filename alone, from a test file."""
    assert is_test_file("lib/streamlit/testing/v1/app_test.py") is True


def test_check_autoclose_without_fix_flags_test_only_pr():
    result = check_autoclose_without_fix(
        6021, "fix(mem0): add test for issue #5915", "Fixes #5915",
        [{"filename": "tests/test_issue_5915.py"}],
    )
    assert result is not None
    assert result["linked_issue"] == 5915


def test_check_autoclose_without_fix_clears_healthy_pr():
    result = check_autoclose_without_fix(
        6050, "fix(vector-store): reset async factory cache",
        "Fixes #5915 properly by clearing the factory fast path.",
        [
            {"filename": "mem0/memory/main.py"},
            {"filename": "tests/test_issue_5915.py"},
        ],
    )
    assert result is None


def test_check_autoclose_without_fix_ignores_boilerplate_reference():
    """End-to-end: a PR that never really claims to close anything, because
    its only '#123' is unedited template text, must not be flagged at all —
    even though its diff happens to touch only test files."""
    result = check_autoclose_without_fix(
        13580,
        "Split stdlib types tests into dedicated test files",
        '## Related issue number\n<!-- WARNING: please use "fix #123" style '
        "references so the issue is closed when this PR is merged. -->",
        [{"filename": "tests/test_types.py"}],
    )
    assert result is None
