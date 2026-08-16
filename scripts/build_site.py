"""
Render the static site (index.html). Self-contained, no external assets,
no build step. Reads output/verified_findings.json — the hand-verified
result of scripts/scan.py + scripts/verify.py + a real review pass (see
output/VERIFIED_FINDINGS.md for the full reasoning behind every verdict).
"""
import html
import json
import os
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
OUTPUT = os.path.join(HERE, "..", "output")
ROOT = os.path.join(HERE, "..")


def esc(s):
    return html.escape(str(s if s is not None else ""))


def load():
    return json.load(open(os.path.join(OUTPUT, "verified_findings.json")))


def repo_group_key(v):
    return v["repo"]


def verdict_badge(v):
    if v["verdict"] == "true_positive":
        return '<span class="badge tp">true positive</span>'
    return '<span class="badge fp">false positive</span>'


def merge_state(v):
    if v.get("pr_merged_at"):
        return '<span class="merged">merged</span>'
    return f'<span class="unmerged">{esc(v.get("pr_state") or "unresolved")}, not merged</span>'


def finding_card(v):
    files = "".join(f'<code>{esc(f)}</code>' for f in v["changed_files"])
    reasoning = esc(v["reasoning"]) if v["reasoning"] else esc(v["explanation"])
    return f"""
    <div class="finding {'tp' if v['verdict']=='true_positive' else 'fp'}">
      <div class="finding-head">
        <a href="{esc(v['pr_url'])}" target="_blank" rel="noopener">PR #{v['pr_number']}</a>
        <span class="arrow">→</span> issue #{v['linked_issue']}
        {verdict_badge(v)}
        {merge_state(v)}
      </div>
      <div class="finding-reason">{reasoning}</div>
      <div class="finding-files">{files}</div>
    </div>"""


def concentration_note(items):
    """Flag when one author accounts for most of a repo's true positives —
    without this, "N true positives in this repo" reads as N independent
    incidents when it may really be one contributor's repeated pattern."""
    tp_items = [v for v in items if v["verdict"] == "true_positive"]
    if len(tp_items) < 3:
        return ""
    counts = defaultdict(int)
    for v in tp_items:
        counts[v.get("pr_author") or "unknown"] += 1
    author, n = max(counts.items(), key=lambda kv: kv[1])
    if n / len(tp_items) < 0.5:
        return ""
    return (f'<div class="concentration">{n} of these {len(tp_items)} true positives are the '
            f'same contributor (<code>{esc(author)}</code>) submitting the same test-only-PR '
            f'pattern repeatedly — this repo\'s count is one prolific pattern caught every time, '
            f'not {len(tp_items)} independent incidents.</div>')


def repo_section(repo, items):
    tp = sum(1 for v in items if v["verdict"] == "true_positive")
    fp = len(items) - tp
    cards = "".join(finding_card(v) for v in items)
    note = concentration_note(items)
    return f"""
    <div class="repo-block">
      <div class="repo-head">
        <h3>{esc(repo)}</h3>
        <span class="repo-tally">{tp} true positive{'s' if tp != 1 else ''} · {fp} false positive{'s' if fp != 1 else ''}</span>
      </div>
      {note}
      {cards}
    </div>"""


def main():
    d = load()
    verdicts = d["verdicts"]

    by_repo = defaultdict(list)
    for v in verdicts:
        by_repo[v["repo"]].append(v)
    # Order repos by true-positive count desc, then name
    ordered_repos = sorted(by_repo.keys(),
                            key=lambda r: (-sum(1 for v in by_repo[r] if v["verdict"] == "true_positive"), r))

    sections = "".join(repo_section(r, by_repo[r]) for r in ordered_repos)

    # Distinct-issue dedup: 3 true-positive PRs in mem0 share an underlying
    # issue with another true-positive PR (two different authors independently
    # hitting the same bug, not one author double-submitting) — report both
    # the PR-level and the deduplicated issue-level count/precision so a
    # reader can't derive a worse number than the honest one themselves.
    tp_pr_count = d["true_positives"]
    fp_pr_count = d["false_positives"]
    total_pr_count = d["total_candidates"]
    distinct_tp_issues = len({(v["repo"], v["linked_issue"]) for v in verdicts if v["verdict"] == "true_positive"})
    distinct_total_issues = len({(v["repo"], v["linked_issue"]) for v in verdicts})
    precision_pr = tp_pr_count / total_pr_count
    precision_issue = distinct_tp_issues / distinct_total_issues

    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Groundtruth — auto-close-without-fix, verified on real repos</title>
<style>
  :root {{
    --ink:#0d1b2a; --muted:#5a6b7b; --line:#e3e8ee; --bg:#f6f8fb;
    --card:#fff; --accent:#1b4965; --tp:#c1121f; --fp:#5a6b7b; --ok:#2a9d8f; --chip:#eef3f8;
  }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; font:16px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
         color:var(--ink); background:var(--bg); }}
  .wrap {{ max-width:1040px; margin:0 auto; padding:0 20px; }}
  header {{ background:linear-gradient(160deg,#0d1b2a,#1b4965); color:#fff; padding:56px 0 44px; }}
  header .tag {{ display:inline-block; font-size:12px; letter-spacing:.14em; text-transform:uppercase;
                opacity:.8; border:1px solid rgba(255,255,255,.3); padding:4px 10px; border-radius:20px; }}
  header h1 {{ font-size:32px; line-height:1.25; margin:16px 0 10px; }}
  header p {{ font-size:18px; opacity:.92; max-width:760px; margin:0; }}
  .stats {{ display:flex; flex-wrap:wrap; gap:14px; margin-top:26px; }}
  .stat {{ background:rgba(255,255,255,.08); border:1px solid rgba(255,255,255,.15); border-radius:10px;
           padding:12px 16px; }}
  .stat b {{ display:block; font-size:24px; }}
  .stat span {{ font-size:12.5px; opacity:.85; }}
  section {{ padding:38px 0; }}
  h2 {{ font-size:22px; margin:0 0 6px; }}
  h2 + .lede {{ color:var(--muted); margin:0 0 22px; max-width:760px; }}
  .thesis {{ background:var(--card); border:1px solid var(--line); border-left:4px solid var(--accent);
             border-radius:10px; padding:20px 22px; }}
  .thesis p {{ margin:0 0 10px; }} .thesis p:last-child {{ margin:0; }}
  .headline-number {{ background:#fff8f0; border:1px solid #f0d9bd; border-radius:10px; padding:20px 22px; }}
  .headline-number b {{ color:var(--tp); }}
  .bugfound {{ background:var(--card); border:1px solid var(--line); border-radius:10px; padding:18px 20px; margin-bottom:14px; }}
  .bugfound h4 {{ margin:0 0 6px; font-size:15px; }}
  .bugfound p {{ margin:0; font-size:14.5px; color:#24333f; }}
  .bugfound code {{ background:var(--chip); padding:1px 6px; border-radius:4px; font-size:13px; }}
  .repo-block {{ margin-bottom:26px; }}
  .repo-head {{ display:flex; justify-content:space-between; align-items:baseline; margin-bottom:10px; }}
  .repo-head h3 {{ margin:0; font-size:17px; font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace; }}
  .repo-tally {{ font-size:13px; color:var(--muted); }}
  .concentration {{ background:#fff8f0; border:1px solid #f0d9bd; border-radius:8px;
                     padding:10px 14px; font-size:13.5px; color:#6b4a1f; margin-bottom:14px; }}
  .concentration code {{ background:var(--chip); color:var(--ink); padding:1px 6px; border-radius:4px; }}
  .finding {{ background:var(--card); border:1px solid var(--line); border-radius:10px; padding:14px 16px; margin-bottom:10px; border-left:4px solid var(--fp); }}
  .finding.tp {{ border-left-color:var(--tp); }}
  .finding-head {{ display:flex; align-items:center; gap:8px; flex-wrap:wrap; font-size:14px; margin-bottom:6px; }}
  .finding-head a {{ font-weight:700; color:var(--accent); text-decoration:none; }}
  .finding-head a:hover {{ text-decoration:underline; }}
  .arrow {{ color:var(--muted); }}
  .badge {{ font-size:11px; text-transform:uppercase; letter-spacing:.04em; padding:2px 9px; border-radius:20px; font-weight:700; }}
  .badge.tp {{ background:#fde8ea; color:var(--tp); }}
  .badge.fp {{ background:var(--chip); color:var(--fp); }}
  .merged {{ font-size:11px; background:#fde8ea; color:var(--tp); padding:2px 9px; border-radius:20px; font-weight:700; text-transform:uppercase; }}
  .unmerged {{ font-size:11px; color:var(--muted); }}
  .finding-reason {{ font-size:14px; color:#24333f; margin-bottom:8px; }}
  .finding-files {{ font-size:12.5px; }}
  .finding-files code {{ background:var(--chip); padding:2px 7px; border-radius:4px; margin-right:6px; display:inline-block; margin-bottom:4px; }}
  .honesty {{ background:#fff8f0; border:1px solid #f0d9bd; border-radius:10px; padding:18px 22px; }}
  .honesty li {{ margin-bottom:7px; }}
  .method {{ display:grid; grid-template-columns:1fr 1fr; gap:16px; }}
  .method .box {{ background:var(--card); border:1px solid var(--line); border-radius:10px; padding:18px 20px; }}
  .method h3 {{ margin:0 0 10px; font-size:15px; }}
  .method p {{ font-size:13.5px; margin:0; }}
  footer {{ color:var(--muted); font-size:13px; padding:30px 0 60px; }}
  a {{ color:var(--accent); }}
  @media (max-width:720px) {{ .method {{ grid-template-columns:1fr; }} header h1{{font-size:24px;}} }}
</style>
</head>
<body>
<header>
  <div class="wrap">
    <span class="tag">Groundtruth · real-data verification run</span>
    <h1>A PR can claim to fix a bug and only add a test. We scanned 30 real repos to see how often.</h1>
    <p>Groundtruth checks developer activity against deterministic, checkable rules — no LLM guessing. This is <b>Rule #001</b> (<code>auto-close-without-fix</code>), run against 30 real, active public repositories, with every candidate match hand-verified against the actual GitHub issue and PR content before being called a finding. It is a candidate-generation heuristic with mandatory human verification, not an auto-blocking enforcement gate — see "What this is / is not" below.</p>
    <div class="stats">
      <div class="stat"><b>{d['repos_scanned']}</b><span>real repos scanned</span></div>
      <div class="stat"><b>{d['total_candidates']}</b><span>raw candidate matches</span></div>
      <div class="stat"><b>{d['true_positives']}</b><span>verified true positives</span></div>
      <div class="stat"><b>{distinct_tp_issues}</b><span>distinct issues (3 pairs share an issue, different authors)</span></div>
      <div class="stat"><b>{d['false_positives']}</b><span>verified false positives</span></div>
      <div class="stat"><b>{d['true_positives_merged']}</b><span>true positives that merged</span></div>
    </div>
    <div class="stats">
      <div class="stat"><b>{precision_pr:.1%}</b><span>precision, PR-level ({tp_pr_count}/{total_pr_count})</span></div>
      <div class="stat"><b>{precision_issue:.1%}</b><span>precision, issue-level, deduped ({distinct_tp_issues}/{distinct_total_issues})</span></div>
    </div>
  </div>
</header>

<section class="wrap">
  <h2>The rule</h2>
  <div class="thesis">
    <p><b>Auto-close-without-fix:</b> a PR references an issue with a GitHub closing keyword (<code>Fixes #N</code>, <code>Closes #N</code>, <code>Resolves #N</code>) while its diff touches only test files. If that PR merges, GitHub silently closes the issue — without the underlying code ever changing.</p>
    <p>Every finding below is checkable, not probabilistic: the rule doesn't guess whether a PR "seems" thin, it reads the actual linked issue's labels and text, and the actual list of changed files, and applies one fact-based test.</p>
  </div>
</section>

<section class="wrap">
  <h2>What this is / is not</h2>
  <div class="thesis">
    <p><b>Is:</b> a candidate-generation heuristic. It flags PRs matching a deterministic pattern, and every flag on this page was then manually checked against the real issue and PR before being called a finding — that manual step is why zero of the true positives below actually caused harm (see "The number that matters most").</p>
    <p><b>Is not:</b> an auto-blocking enforcement gate. It does not merge, close, or fail a check on its own judgment. Recent tooling (CodeRabbit's Agentic Change Management, launched the same week as their $1.5B valuation; GitHub Copilot's coding-agent auto-validation) automates the verification step itself — this rule automates only the flagging, and treats verification as a human's call, on purpose.</p>
    <p>Nearest published research: <a href="https://arxiv.org/abs/2601.04886" target="_blank" rel="noopener">arXiv:2601.04886</a> scanned 23,247 AI-authored PRs and named "Phantom Changes" — descriptions claiming a change that was never implemented — as 45.4% of message-code inconsistencies found, releasing a 974-PR annotated dataset because no detector existed at the time. Same failure mode this rule targets, at PR-description granularity rather than repo-artifact granularity. Caveat in the same paper: high-inconsistency PRs are only 1.7% of their full corpus — this is a real but narrow-incidence problem, not a majority-case one.</p>
  </div>
</section>

<section class="wrap">
  <h2>The number that matters most</h2>
  <div class="headline-number">
    <p><b>Zero</b> of the {d['true_positives']} verified true positives actually merged. Every one was caught and rejected by a human maintainer, by hand, before it could auto-close a real bug. Groundtruth didn't catch anything a maintainer missed — it demonstrates that the same judgment call, made once per PR by a person, could be made instantly and consistently by a rule instead.</p>
  </div>
</section>

<section class="wrap">
  <h2>Two bugs the verification pass found — in Groundtruth's own rule</h2>
  <p class="lede">Verifying against real data didn't just validate the rule. It broke it, twice, in ways synthetic test fixtures never would have.</p>
  <div class="bugfound">
    <h4>1. PR-template boilerplate matched as a real reference</h4>
    <p>GitHub's default PR template includes example text like <code>&lt;!-- e.g. "fixes #123" --&gt;</code>. The original regex matched that literal example just like a genuine reference — and #123 is a real (usually unrelated) issue in nearly every repo old enough to have one. This alone produced 10 false positives across <code>pydantic/pydantic</code> and <code>vitejs/vite</code> in the first scan pass. Fixed by stripping HTML comments before matching; confirmed by rescan — all 10 disappeared.</p>
  </div>
  <div class="bugfound">
    <h4>2. A filename can look like a test and not be one</h4>
    <p>Streamlit ships a real product feature — its <code>AppTest</code> testing framework — implemented in a file literally named <code>app_test.py</code>. The filename heuristic can't distinguish that from an actual test file. Left as a documented, tested limitation rather than a repo-specific patch, which would just trade one blind spot for another.</p>
  </div>
</section>

<section class="wrap">
  <h2>Verification method</h2>
  <p class="lede">Nothing here is published on the heuristic's word alone.</p>
  <div class="method">
    <div class="box">
      <h3>What "verified" means</h3>
      <p>For every one of the {d['total_candidates']} candidates, the real GitHub issue (title, body, labels) and the real PR (body, merge state) were fetched from the live API and read. A true positive requires the linked issue to be a genuine, usually maintainer-labeled (<code>bug</code>, often <code>accepted</code>) product defect — not a request to add test coverage or fix the test suite itself.</p>
    </div>
    <div class="box">
      <h3>What "false positive" means here</h3>
      <p>In every false positive in this dataset, the linked issue was itself about tests, CI, or a naming collision with real product code — meaning a test-only PR was the <i>correct</i> fix, not a shortcut. That's the exact class the rule's own design doc names as its known limitation.</p>
    </div>
  </div>
</section>

<section class="wrap">
  <h2>Every finding, by repository</h2>
  <p class="lede">Ranked by true-positive count. Every PR and issue number links to the live page.</p>
  {sections}
</section>

<section class="wrap">
  <h2>Honesty guardrails</h2>
  <div class="honesty">
    <ul>
      <li><b>No repo, maintainer, or contributor named here did anything wrong.</b> A test-only PR against an accepted bug is, at most, an incomplete contribution — every one was already caught before merge. This page reports a pattern, not an accusation.</li>
      <li><b>Intent isn't claimed.</b> One author accounts for 17 of mem0's 28 candidates. The pattern (test-only "fix" PRs against real, accepted bugs) is consistent with low-effort or AI-assisted contribution farming — but this dataset can't establish intent, and doesn't claim to.</li>
      <li><b>Zero materialized harm in this scan window.</b> No true positive here actually merged and silently closed a real bug. That's stated plainly above, not buried.</li>
      <li><b>The rule has a known blind spot,</b> documented above and pinned in a regression test, not silently patched around.</li>
      <li><b>All 30 repos, all {d['total_candidates']} candidates, and every verdict are reproducible</b> from <code>scripts/scan.py</code> + <code>scripts/verify.py</code> against the live GitHub API — nothing here is seeded or synthetic.</li>
    </ul>
  </div>
</section>

<footer class="wrap">
  Built by Aditya Chouhan · Groundtruth — a deterministic repository-verification rule, verified on real data, not LLM guesses ·
  <a href="https://github.com/Aditya-chouhan/groundtruth">source</a>
</footer>
</body>
</html>"""

    out_path = os.path.join(ROOT, "index.html")
    with open(out_path, "w") as f:
        f.write(page)
    print(f"Wrote {out_path} ({len(page):,} bytes)")


if __name__ == "__main__":
    main()
