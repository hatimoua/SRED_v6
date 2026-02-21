# SR&ED Platform — Coding-Assistant Prompt Pack

This is the canonical, phased prompt series for AI coding assistants working on the SREDv5 → First Client refactor.
Each Phase is a self-contained unit of work. Complete and verify one Phase before starting the next.

**Always read `docs/REFRACTORING_BIBLE.md` before writing any code.**

---

## Phase 1 — Stabilize & Prepare the Refactor Boundary ✅

**Goal:** No functional rewrites yet. Add canonical docs, fix the nav regression, create an import-boundary guard test, and harden `sred doctor` to exit non-zero on failures.

### Prompt 1.1 — Add `docs/` folder
- Copy `REFRACTORING_BIBLE (2).md` → `docs/REFRACTORING_BIBLE.md`
- Create `docs/CODING_ASSISTANT_PROMPT_PACK.md` (this file)
- Create `docs/README.md` explaining both files
- Add `## Docs` section to root `README.md`

### Prompt 1.2 — Fix navigation regression
- Pages `5_search.py` and `6_csv_tools.py` exist on disk but are absent from `streamlit_app.py`
- Insert them in correct numeric order (between page 4 and page 7)
- Verify: `python -m compileall src/sred` + Streamlit starts with all 11 pages

### Prompt 1.3 — Import boundary guard test
- Create `tests/test_import_boundaries.py`
- AST-based scan of `src/sred/ui/` for banned imports (`sqlmodel`, `sqlalchemy`, `sred.models`, `sred.db`, `sred.domain.models`)
- Uses an explicit legacy allowlist — passes now, fails if any NEW file violates the rule

### Prompt 1.4 — Harden `sred doctor`
- Collect failures into a list; exit non-zero when any check fails
- Add DB file writability check
- Add `OPENAI_EMBEDDING_MODEL` non-empty check
- Restructure output: all checks print, then summary with pass/fail count

**Verification:**
```bash
uv run python -m compileall src/sred
uv run pytest tests/test_import_boundaries.py -v
uv run pytest
uv run sred doctor
OPENAI_API_KEY="" uv run sred doctor; echo "Exit: $?"
```

---

## Phase 2 — FastAPI Skeleton + Repository Layer (Planned)

**Goal:** Introduce the FastAPI app factory and the first repository + UoW layer, without removing any Streamlit functionality.

### Prompt 2.1 — FastAPI app factory
- Create `src/sred/api/app.py` with `create_app()` factory
- Create `src/sred/api/deps.py` with UoW and settings dependencies
- Health endpoint: `GET /health`
- Wire into `uv run sred api` CLI command
- Verify: `uv run sred api` starts; `curl localhost:8000/health` returns 200

### Prompt 2.2 — Engine + UoW infrastructure
- Create `src/sred/infra/db/engine.py` — engine created once per process, WAL mode enabled
- Create `src/sred/infra/db/uow.py` — UnitOfWork (session per request, commit/rollback)
- Write unit tests for UoW lifecycle

### Prompt 2.3 — First repositories (Runs, Files)
- Create `src/sred/infra/db/repositories/runs.py` — `RunRepository`
- Create `src/sred/infra/db/repositories/files.py` — `FileRepository`
- No business logic in repositories; DB reads/writes only
- Wire into Runs and Files API routers
- Write integration tests using an in-memory SQLite fixture

### Prompt 2.4 — Pydantic DTOs for Runs + Files
- Create `src/sred/api/schemas/runs.py` — request/response DTOs
- Create `src/sred/api/schemas/files.py` — request/response DTOs
- Routers must return DTOs only (never ORM objects)
- Add a test that asserts no router response contains an ORM instance

---

## Phase 3 — LangGraph Orchestration Migration (Planned)

**Goal:** Replace the hand-rolled agent loop in `runner.py` with a LangGraph graph that uses `SqliteSaver` for checkpointing.

### Prompt 3.1 — LangGraph graph skeleton
- Create `src/sred/orchestration/graph.py` with `build_graph()` factory
- Create `src/sred/orchestration/state.py` with `GraphState` schema + `GRAPH_STATE_VERSION`
- Wire `SqliteSaver` from `langgraph-checkpoint-sqlite`
- `thread_id = "{run_id}:{session_id}"` deterministic key
- CLI command: `sred checkpoints reset --run-id X`

### Prompt 3.2 — Deterministic context nodes
- Implement nodes: `ensure_thread_id`, `restore_or_init_state`, `load_world_snapshot`, `build_anchor_lane`, `memory_retrieve`, `retrieve_evidence_pack`, `context_compiler`
- All are deterministic (no LLM calls)
- Unit tests with a fake DB fixture

### Prompt 3.3 — Planner + Tool executor nodes
- Implement `block_now?`, `human_gate`, `planner`, `done?`, `tool_executor`, `gate_evaluator`, `summarizer`, `finalizer`
- Wire the canonical Mermaid flow from the Bible §7.6
- Integration test: fake LLM client, verify state transitions

### Prompt 3.4 — Agent API endpoint
- `POST /runs/{run_id}/agent/message` drives LangGraph workflow
- Returns structured payload: `status`, `answer`, `refs`, `next_actions`
- Replace `runner.py` usage in the Agent page (page 7) with API call

---

## Phase 4 — VectorStore Abstraction (Planned)

**Goal:** Replace brute-force numpy cosine search with a `VectorStore` interface backed by `sqlite-vec`.

### Prompt 4.1 — VectorStore interface
- Create `src/sred/infra/search/vector_store.py` — abstract `VectorStore` interface
- Methods: `upsert(id, embedding, metadata)`, `query(embedding, top_k, filters)`, `delete(id)`
- Embedding model name + dimension stored with each embedding

### Prompt 4.2 — sqlite-vec implementation
- Create `src/sred/infra/search/vector_sqlite.py` — `SqliteVectorStore` implementing `VectorStore`
- Use `sqlite-vec` extension
- Unit tests with a real sqlite-vec connection fixture

### Prompt 4.3 — Migration of existing embeddings
- CLI command: `sred db migrate-vectors` — re-embeds segments without embeddings or with model mismatch
- Model mismatch detection: stored model name != current config → re-embed or error

---

## Phase 5 — DuckDB Hardening (Planned)

**Goal:** Harden the CSV analytics surface so prompt-injection cannot read arbitrary local files.

### Prompt 5.1 — DuckDB sandbox
- Create `src/sred/infra/analytics/duckdb_sandbox.py` — `DuckDBSandbox`
- Create connection with external access disabled
- Block: `read_*` path functions, `COPY`, `ATTACH`, `INSTALL`, `LOAD`, `PRAGMA`, `EXPORT`

### Prompt 5.2 — SQL safety validator
- Create `src/sred/infra/analytics/sql_safety.py` — SELECT-only allowlist validator
- Reject any query not starting with `SELECT`/`WITH`
- Token-level scan for prohibited keywords
- Default row limit (200), query timeout, max bytes

### Prompt 5.3 — Tests
- Unit tests: blocked queries return errors, allowed queries pass through
- Regression tests: `read_csv_auto('/etc/passwd')` is blocked

---

## Phase 6 — Streamlit as Thin Client (Planned)

**Goal:** Migrate each Streamlit page from direct ORM/DB calls to API client calls. Remove UI from the legacy allowlist in the boundary test as pages are migrated.

### Prompt 6.1 — API client wrapper
- Create `src/sred/ui/api_client.py` — typed wrapper over `httpx` calling FastAPI
- One method per endpoint

### Prompt 6.2 — Migrate pages (one per prompt)
- For each page (1_run through 11_ledger): replace ORM imports with API client calls
- Remove the page from the legacy allowlist in `tests/test_import_boundaries.py`
- Verify: boundary test still passes (shorter allowlist = progress)

---

## ADR Log

Create `docs/adr/ADR-XXXX-title.md` for every architectural decision. Template:

```markdown
# ADR-XXXX — Title

**Date:** YYYY-MM-DD
**Status:** Proposed | Accepted | Superseded

## Context
What is the situation that led to this decision?

## Decision
What did we decide?

## Consequences
What are the trade-offs and downstream effects?
```

---

*This prompt pack is maintained alongside `docs/REFRACTORING_BIBLE.md`. Update it as phases complete or new phases are defined.*
