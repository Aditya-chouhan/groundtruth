# Groundtruth — Claude Code Context

## What this is
Groundtruth is a multi-tenant SaaS product that gives engineering teams a complete AI Company Brain.
It ingests repository activity (PRs, issues, commits), automatically compiles rulebooks (CLAUDE.md, SKILL.md, AGENTS.md), and exposes a live webhook runtime ("ContextOps") to check developer activities against rules.

## Owner
Aditya Chouhan (adityachouhan5555@gmail.com)
Claude Code does all the building. Aditya directs.

## The core problem we're solving
AI coding agents (like Claude Code, Cursor) fail or drift because repository-specific rules (CLAUDE.md, SKILL.md) go stale. Groundtruth solves this by:
1. **Auto-extraction**: Ingesting patterns from developer activity.
2. **Auto-compilation**: Keeping CLAUDE.md/SKILL.md current without human manual documentation.
3. **Closed-loop checking**: Webhooks auditing developer actions against rules in real-time.

## Tech stack
- **Frontend**: Next.js 14 + TypeScript + Tailwind CSS
- **Backend**: Python 3.11 + FastAPI
- **Database**: PostgreSQL + pgvector (embeddings + structured data)
- **LLM**: Claude API (claude-sonnet-4-6, with prompt caching) — primary
- **Queue**: Redis + Celery (indexing & check tasks)

## Project structure
```
groundtruth/
├── app/
│   ├── backend/           # FastAPI Python app
│   │   ├── main.py
│   │   ├── agents/        # Domain agents (RepositoryAgent)
│   │   ├── routers/       # API route handlers (auth, workspaces, repositories, chat)
│   │   ├── models/        # DB models (SQLAlchemy - workspace, repository)
│   │   ├── memory/        # RAG + vector store utilities
│   │   └── tools/         # Shared tools (github, git, search)
│   └── frontend/          # Next.js app
│       └── src/
│           ├── app/       # App router pages
│           ├── components/ # UI components
│           └── lib/       # API client, utils
├── docs/
│   ├── ARCHITECTURE.md
│   ├── product-requirements.md
├── data/
│   └── schemas/           # DB schema definitions
└── docker-compose.yml
```

## Groundtruth Design Rule
> **Every finding this system surfaces must be a checkable, deterministic fact, not a probabilistic LLM guess.**

## Known constraints
- Claude API: use prompt caching aggressively (large system prompts cache after 1024 tokens)
- Multi-tenancy: every DB record must have a `workspace_id` — no exceptions
- Context limit: each agent call must stay under 100k tokens total
