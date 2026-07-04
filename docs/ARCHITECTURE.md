# Groundtruth — Technical Architecture

## Overview

Groundtruth is built as a **ContextOps platform** for engineering teams. It keeps AI agent context files (CLAUDE.md, SKILL.md, AGENTS.md) synchronized with codebase practices by analyzing developer activity and webhook events.

```
┌─────────────────────────────────────────────────────────┐
│                     USER INTERFACE                       │
│      Dashboard (Next.js) + Chat (streaming rules)       │
└────────────────────────┬────────────────────────────────┘
                         │ HTTP / WebSocket
┌────────────────────────▼────────────────────────────────┐
│                    API GATEWAY (FastAPI)                  │
│             Auth · Webhooks · Router / Chat              │
└──────┬────────────────────────────────┬─────────────────┘
       │                                │
┌──────▼──────┐                 ┌───────▼───────┐
│ REPOSITORY  │                 │   INDEXER     │
│   AGENT     │                 │   (Celery)    │
│             │                 │               │
│ Answers     │                 │ Ingests PRs,  │
│ questions   │                 │ commits,      │
│ about rules │                 │ compiles md   │
└──────┬──────┘                 └───────┬───────┘
       │                                │
       ▼                                ▼
┌─────────────────────────────────────────────────┐
│                  MEMORY LAYER                    │
│                                                  │
│  PostgreSQL (structured) + pgvector (semantic)   │
│  repositories · rulebooks · activities · findings│
└─────────────────────────────────────────────────┘
```

---

## Key Modules

### 1. Ingestion Layer
- Connects to GitHub via GitHub App OAuth and webhook events.
- Ingests PRs, issues, commits, and discussions.
- Stores metadata in `repository_activities` and splits context for semantic embedding in `knowledge_chunks`.

### 2. Semantic Compiler (The Brain)
- Takes ingested activities and groups them by module/feature.
- Uses `claude-sonnet-4-6` to identify patterns, conventions, style guidelines, and unwritten rules.
- Compiles findings into executable `CLAUDE.md` and `SKILL.md` structures.

### 3. Check Layer (The Runtime / OS)
- Receives git pushes and pull request webhook updates.
- Executes check routines against compiled rules.
- **Design Rule**: All checks must evaluate checkable, deterministic facts, not probabilistic LLM predictions.
- Inserts warnings and recommendations into `webhook_findings`.

---

## Data Model

```sql
workspaces             (id, name, domain, created_at)
users                  (id, workspace_id, email, hashed_password, role)
repositories           (id, workspace_id, name, owner, branch, status)
repository_activities  (id, repository_id, workspace_id, activity_type, external_id, title, payload)
rulebooks              (id, repository_id, workspace_id, filename, content, version, is_current)
webhook_findings       (id, repository_id, workspace_id, event_type, external_id, severity, title, details)
knowledge_chunks       (id, workspace_id, source_type, source_id, content, embedding vector(1536))
```
