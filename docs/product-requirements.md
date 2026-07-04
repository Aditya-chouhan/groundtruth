# Groundtruth — Product Requirements

## Vision
The AI Company Brain for software engineering teams. It keeps your rules current by watching what your team actually does, ensuring AI coding assistants (Claude Code, Cursor) always align with codebase reality.

## Target Customer (MVP)
**Primary:** Sub-20-person, AI-native software engineering teams using Claude Code, Cursor, or similar tools.
- Wear multiple hats, moving extremely fast.
- Knowledge transfer and developer onboarding are immediate bottlenecks as teams scale past 3-5 devs.
- Stale CLAUDE.md files cause AI to generate outdated, bug-prone, or off-style code.

## The Core Promise
> "Connect your repo. Keep your CLAUDE.md current automatically. Check developer actions against rules in real-time."

## MVP Feature List

### Must have (MVP — 3 weeks)
- [ ] Workspace creation + basic GitHub Auth
- [ ] Repository setup wizard (connect GitHub repo → auto-indexing)
- [ ] Auto-compilation of rulebooks (`CLAUDE.md`, `SKILL.md`) based on past PRs, commits, and issues
- [ ] Webhook integration: pull_request webhook checks PR details against compiled rules (e.g. flagging test-only auto-closes)
- [ ] Workspace dashboard: view compiled rulebooks, live findings, repository status
- [ ] Query Brain chat interface: ask questions about repository standards and guidelines

### Should have (V1.1 — weeks 4-6)
- [ ] Slack integration: send alerts when rules are violated or updated
- [ ] Linear/Jira integration: extract rules from incident postmortems and issues
- [ ] CLI utility: `/sync-groundtruth` or local config hooks to sync CLAUDE.md directly in dev environments

---

## Success Metrics (MVP)
- Week 3: Groundtruth indexed and checked on 3+ real repositories
- Week 4: First external design partner using Groundtruth in production
- Week 6: YC Fall 2026 application submitted with live validation numbers
