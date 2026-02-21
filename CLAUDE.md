# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

SR&ED Automation Platform — a local-first, AI-powered tool for preparing Canadian Scientific Research & Experimental Development (SR&ED) tax credit claims. It ingests messy evidence (timesheets, payroll, invoices, PDFs), extracts structured data via OCR/vision models, validates cross-source consistency, and produces auditable labour-hour ledgers with confidence scores.

**Always read `REFRACTORING_BIBLE (2).md` before writing any code.** It is the source of truth for every architectural decision until first client delivery.

---

## Commands

```bash
# Setup
uv sync                                          # Create venv + install all deps

# Run
uv run streamlit run streamlit_app.py            # Launch UI (current, pre-refactor)
uv run sred doctor                               # Health check (config, data dir, Python version)
uv run sred db init                              # Initialize SQLite database
uv run sred db reindex                           # Rebuild FTS5 index + regenerate embeddings
uv run sred db search "<query>"                  # Test hybrid search from CLI

# Test
uv run pytest                                    # Run all tests
uv run pytest tests/test_agent.py               # Run a single test file
uv run pytest tests/test_db.py::test_name       # Run a single test
```

**Environment:** Requires `.env` with `OPENAI_API_KEY`. All other settings have defaults in `src/sred/config.py` (Pydantic Settings).

---

## Current Architecture (SREDv5 — being refactored)

### Stack
- **UI:** Streamlit (11 pages, `streamlit_app.py` entry point)
- **Database:** SQLite at `data/sred.db` via SQLModel (SQLAlchemy ORM + Pydantic)
- **Agent:** Hand-rolled OpenAI tool-calling loop in `src/sred/agent/runner.py`
- **Search:** SQLite FTS5 (BM25) + local vector embeddings (numpy cosine, O(n)) fused via Reciprocal Rank Fusion
- **File storage:** `data/runs/<run_id>/uploads/` with SHA-256 deduplication

### Key Modules (current)

| Path | Purpose |
|------|---------|
| `streamlit_app.py` | UI entry point; registers all 11 pages |
| `src/sred/cli.py` | CLI (`sred doctor`, `sred db init/reindex/search`) |
| `src/sred/config.py` | Pydantic Settings; LLM model names configured here |
| `src/sred/db.py` | SQLite engine + session factory |
| `src/sred/agent/runner.py` | Agent loop: builds context, calls OpenAI, dispatches tools |
| `src/sred/agent/registry.py` | Tool registry: `register_tool()`, `get_tool_handler()`, `get_openai_tools_schema()` |
| `src/sred/agent/tools.py` | ~1,400 lines — 20 registered tool handlers |
| `src/sred/ingest/process.py` | File ingestion (vision/OCR, CSV profiling, DOCX, text) |
| `src/sred/search/hybrid_search.py` | FTS5 + vector + RRF fusion |
| `src/sred/gates.py` | `update_run_gate_status()` — transitions run status on contradictions |
| `src/sred/models/` | 17 SQLModel table definitions |
| `src/sred/ui/pages/` | One file per Streamlit page (1_run through 11_ledger) |
| `src/sred/ui/state.py` | Session state helpers: `get_run_id()`, `set_run_context()` |

### LLM Models (from `config.py`)
- `OPENAI_MODEL_AGENT` = `gpt-5` — agent reasoning loop
- `OPENAI_MODEL_VISION` = `gpt-5-mini` — OCR/PDF vision extraction
- `OPENAI_MODEL_STRUCTURED` = `gpt-4o-2024-08-06` — JSON structured outputs
- `OPENAI_EMBEDDING_MODEL` = `text-embedding-3-large` — segment embeddings

### World Model & Gating (non-negotiable, must be preserved in refactor)
Human decisions are immutable once locked:
1. **Contradiction** — created when validation fails (e.g., payroll vs. timesheet mismatch > 5%). `BLOCKING` severity sets `run.status = NEEDS_REVIEW`.
2. **ReviewTask** — action item for human review.
3. **ReviewDecision** — human resolution.
4. **DecisionLock** — immutable; `has_active_lock(run_id, issue_key)` prevents agent from reopening.

All extractions and transformations must be **source-linked** (`source_file_id`, `page_number`, `row_number`). All tool/LLM calls are logged to `ToolCallLog` / `LLMCallLog`.

---

## Target Architecture (Refactoring Bible — first client delivery)

### North Star
Streamlit → thin HTTP client. FastAPI → core backend. LangGraph → orchestration. Repository + Unit of Work → DB access. VectorStore abstraction → replaces brute-force numpy.

### Target Repo Layout
```
src/sred/
  api/
    app.py                # FastAPI app factory
    deps.py               # UoW + settings dependencies
    routers/              # runs, files, ingest, people, aliases, ledger,
                          #   tasks, search, agent, exports, admin
    schemas/              # Pydantic DTOs (NO ORM objects)
  domain/
    models/               # ORM models (backend only)
    rules/                # pure domain rule functions
    types.py              # enums, typing
  services/               # one use-case per service file
  orchestration/
    graph.py              # LangGraph graph definition
    state.py              # GraphState schema
    nodes/                # plan, execute, gate, summarize, etc.
  infra/
    db/
      engine.py           # engine creation (once per process)
      uow.py              # UnitOfWork (session per request)
      repositories/       # DB reads/writes only — no business logic
    llm/
      client.py           # OpenAI adapter (LLMClient interface)
      prompts.py
    search/
      vector_store.py     # VectorStore interface (Strategy Pattern)
      vector_sqlite.py    # sqlite-vec backed implementation
    analytics/
      duckdb_sandbox.py   # hardened DuckDB (external access disabled)
      sql_safety.py       # SELECT-only allowlist validator
    observability/
  ui/
    streamlit_app.py      # nav + API base URL config only
    pages/                # thin pages — call API, render results
    api_client.py         # typed API client wrapper
  cli/
    main.py               # Typer entrypoint
    commands/
```

### Hard UI Rule
`src/sred/ui/` may only import: `sred/api/schemas/*`, `sred/ui/api_client.py`, stdlib + UI libs.
**Never import:** `sred/domain/models/*`, `sred/infra/db/*`, `sqlmodel`, `sqlalchemy`.

### Hard API DTO Rule
FastAPI routers must **never** return ORM instances — only pure Pydantic DTOs. Map ORM→DTO inside the Service layer. This prevents `DetachedInstanceError`, lazy-loading outside session scope, and N+1 regressions.

### LangGraph Orchestration (OpenClaw-style)
Use LangGraph's native `SqliteSaver` from `langgraph-checkpoint-sqlite`. Do not hand-roll checkpoint tables.

- `thread_id = "{run_id}:{session_id}"` — deterministic
- Maintain `GRAPH_STATE_VERSION` constant
- Provide CLI command to clear/reset checkpoints per run

**Required nodes (in order):** `ensure_thread_id` → `restore_or_init_state` → `load_world_snapshot` → `build_anchor_lane` → `memory_retrieve` → `retrieve_evidence_pack` → `context_compiler` → `block_now?` → (blocked: `human_gate`) / (not blocked: `planner` → `done?` → tool loop: `tool_executor` → `gate_evaluator` → loop or `human_gate`) → `summarizer` → `finalizer`

The **ContextPacket** (built deterministically each cycle) has four lanes: world snapshot (DB truth), people/time anchor (always-on facts), memory summaries, evidence pack (with citations).

### DuckDB Hardening (mandatory)
- Create connection with external access disabled
- Block all `read_*` path functions, `COPY`, `ATTACH`, `INSTALL`, `LOAD`, `PRAGMA`, `EXPORT`
- Enforce SELECT-only: reject any query not starting with `SELECT`/`WITH`
- Default row limit (200), query timeout, max bytes returned

### Database Rules
- Engine created **once** per backend process
- Session created **per request** (FastAPI dependency)
- Sessions never created inside Streamlit
- Enable WAL mode on SQLite
- `SQLModel.metadata.create_all(engine)` on startup is acceptable until first client; Alembic planned before production

### VectorStore Refactor
Replace brute-force numpy with a `VectorStore` interface. Preferred: `sqlite-vec` extension. Embedding model name + dimension must be stored with each embedding; query model must match or trigger re-embed/error.

---

## Design Patterns Enforced (Bible §5)
- **Repository Pattern** — no business logic inside repositories
- **Unit of Work** — single request/session boundary
- **Command Pattern** — each tool has: name, schema, handler, idempotency notes
- **Strategy Pattern** — `VectorStore` and `LLMClient` are swappable interfaces
- **Adapter Pattern** — wrap OpenAI SDK behind `LLMClient`; DuckDB behind `DuckDBSandbox`
- **Factory** — `create_app()` and `build_graph()` accept settings

## Rules of Engagement (Bible §16)
1. Make small, reviewable changes
2. Preserve contracts; introduce new ones deliberately
3. Add tests for every new boundary
4. Never fix by hack in Streamlit — fix in backend boundaries
5. Any change touching world model gates requires a regression test
