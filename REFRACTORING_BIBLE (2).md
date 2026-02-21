# SR&ED Platform Refactoring Bible (SREDv5 → First Client)

**Audience:** Engineering + AI team building the SR&ED Automation
Platform\
**Scope:** "Bible" to guide every change until the **first client
delivery** (local-only).\
**Source of truth:** This bible + the current Solution Design v5.0
(living doc).

------------------------------------------------------------------------

## 0. North Star

Deliver a **local-first** SR&ED preparation platform that is:

-   **Correct**: accounting-grade tables, validations, explicit
    contradictions/gates
-   **Auditable**: full trace of evidence → extraction → decision →
    ledger
-   **Composable**: UI, orchestration, and persistence decoupled (no
    monolith scripts)
-   **Safe-by-default**: hardened analytics surface (DuckDB),
    deterministic gates
-   **Fast to iterate**: coding-assistant friendly; clean module
    boundaries; tests

**What we will *not* do before first client:** - Authentication /
multi-tenancy (local-only)\
- Cloud storage, Postgres, pgvector (planned later)\
- A full React/Next.js rewrite (optional later)

------------------------------------------------------------------------

## 1. Non‑Negotiables and Constraints

### 1.1 Constraints (until first client)

-   **Local-only runtime**
    -   Bind services to `127.0.0.1` (not `0.0.0.0`)
    -   Data stored on local disk under `data/`
-   **SQLite is the primary database**
    -   Single file: `data/sred.db`
    -   Must be inspectable in DBeaver
-   **No auth for now**
    -   But design must not *prevent* later auth (keep clean boundaries)

### 1.2 Non‑negotiable product behaviors

-   All extractions + transformations must be **source-linked**
    -   `source_file_id`, `page_number`, `row_number`, etc.
-   Every model decision must have an **audit trail**
    -   Tool/LLM call logs are first-class
-   "World model" gates must remain explicit
    -   Contradiction → ReviewTask → DecisionLock blocks progress when
        needed

------------------------------------------------------------------------

## 2. The Architectural Shift We Are Making

We are **not** rewriting the SR&ED domain. We are **refactoring
boundaries** so we can safely add complexity.

### 2.1 Current pain

-   Streamlit hot reload + ORM imports → mapper collisions
-   UI pages mix:
    -   DB sessions
    -   orchestration
    -   business rules
-   Custom runner loop makes state/memory/resume hard
-   Vector search brute force won't scale
-   DuckDB "CSV SQL" can read arbitrary local files if misused

### 2.2 Target state (until first client)

-   **Streamlit becomes a thin UI client**
-   **FastAPI becomes the core backend boundary**
-   **Service layer owns business rules**
-   **Repository + Unit of Work own DB**
-   **LangGraph owns orchestration** (agent workflow as a state machine)
-   **VectorStore abstraction** replaces brute-force numpy
-   **DuckDB is hardened** with external access disabled + SQL
    allowlisting
-   **DBeaver + CLI** make the DB observable without custom UI hacks

------------------------------------------------------------------------

## 3. Target System Diagram

                     ┌──────────────────────────┐
                     │        Streamlit UI       │
                     │  (thin client, no ORM)    │
                     └─────────────┬────────────┘
                                   │ HTTP (localhost)
                                   ▼
    ┌───────────────────────────────────────────────────────────┐
    │                         FastAPI                             │
    │  Routers: runs, files, ingest, people, aliases, ledger,     │
    │          tasks/gates, search, agent, exports, admin         │
    └─────────────┬───────────────────────────┬──────────────────┘
                  │                           │
                  ▼                           ▼
        ┌───────────────────┐       ┌───────────────────────────┐
        │   Service Layer    │       │     LangGraph Runtime      │
        │ (use-cases + rules)│       │  (plan→tool→gate→resume)  │
        └──────────┬─────────┘       └───────────────┬───────────┘
                   │                                  │
                   ▼                                  ▼
         ┌──────────────────┐              ┌──────────────────────┐
         │ Repositories/UoW  │              │ Tool Registry/Adapters│
         │ (DB access only)  │              │ (LLM, storage, csv)   │
         └──────────┬────────┘              └───────────┬──────────┘
                    │                                   │
                    ▼                                   ▼
             ┌───────────────┐                  ┌───────────────────┐
             │ SQLite (sred)  │                  │ Local filesystem  │
             │ tables + logs  │                  │ uploads, artifacts│
             └───────┬───────┘                  └───────────────────┘
                     │
                     ▼
             ┌──────────────────┐
             │ VectorStore (local)│  (sqlite-backed or local index)
             └──────────────────┘

------------------------------------------------------------------------

## 4. Repo Layout (Target)

**Goal:** Make it impossible to re-couple UI↔DB↔orchestration by
accident.

Recommended structure:

    src/sred/
      api/
        app.py                # FastAPI app factory
        deps.py               # dependencies (UoW, settings)
        routers/
          runs.py
          files.py
          ingest.py
          people.py
          aliases.py
          ledger.py
          tasks.py
          search.py
          agent.py
          exports.py
          admin.py
        schemas/              # Pydantic request/response DTOs (NO ORM)
      domain/
        models/               # ORM models (SQLModel) - backend only
        rules/                # domain rules (pure functions)
        types.py              # enums, typing
      services/
        runs_service.py
        files_service.py
        ingest_service.py
        people_service.py
        aliases_service.py
        ledger_service.py
        search_service.py
        tasks_service.py
        agent_service.py      # orchestration entrypoints
      orchestration/
        graph.py              # LangGraph graph definition
        state.py              # Graph state schema
        nodes/                # plan, execute, gate, summarize, etc.
      infra/
        db/
          engine.py           # engine creation
          uow.py              # UnitOfWork (session per request)
          repositories/       # repositories only (no business logic)
          migrations/         # (optional now; required later)
        llm/
          client.py           # OpenAI adapter
          prompts.py          # shared system prompts
        search/
          vector_store.py     # VectorStore interface
          vector_sqlite.py    # sqlite-backed implementation
          vector_fallback.py  # fallback (HNSW/FAISS) if needed
        analytics/
          duckdb_sandbox.py   # hardened duckdb connection
          sql_safety.py       # allowlist/validation
        observability/
          logging.py          # structured logs + contextvars
          tracing.py          # IDs and helpers
      ui/
        streamlit_app.py      # minimal nav + API base url config
        pages/                # thin UI pages calling API only
        api_client.py         # typed API client wrapper
      cli/
        main.py               # Typer CLI entrypoint
        commands/
          doctor.py
          db.py
          reindex.py
          export.py

**Rule:** `src/sred/ui/` may import **only**: - `sred/api/schemas/*`
(DTOs) - `sred/ui/api_client.py` - standard library + UI libs

UI must **never** import: - `sred/domain/models/*` - `sred/infra/db/*` -
`sqlmodel` / `sqlalchemy`

------------------------------------------------------------------------

## 5. SOLID + Design Patterns We Will Enforce

### 5.1 SOLID, concretely in this codebase

-   **S: Single Responsibility**
    -   UI pages render and call API; nothing else.
    -   Services implement one use-case each.
    -   Repositories do database reads/writes only.
-   **O: Open/Closed**
    -   Add new tools without modifying core orchestration loop
        (registry/graph node dispatch).
    -   VectorStore via Strategy: new backend without changing callers.
-   **L: Liskov Substitution**
    -   Interfaces (`VectorStore`, `LLMClient`, `Storage`) must be
        swappable in tests.
-   **I: Interface Segregation**
    -   Keep small interfaces; don't build a mega "Database" class.
-   **D: Dependency Inversion**
    -   Services depend on repo interfaces, not SQLModel sessions.
    -   Orchestration depends on service/tool interfaces, not concrete
        adapters.

### 5.2 Design Patterns (mandatory)

**Repository Pattern** - `RunRepository`, `FileRepository`, etc. - No
business logic inside repositories.

**Unit of Work** - Single request/session boundary. - Commit/rollback
controlled centrally.

**Command Pattern (Tools)** - Each tool is a "command" with: - name,
schema, handler, idempotency notes - Tool execution is logged
consistently.

**Strategy Pattern** - `VectorStore` interchangeable implementations. -
Embedding model routing strategies later.

**Adapter Pattern** - Wrap OpenAI SDK behind `LLMClient` interface. -
Wrap DuckDB sandbox behind `DuckDBSandbox`.

**Factory** - `create_app()` and `build_graph()` accept settings and
build configured instances.

**Observer / Event Log** - All tool/LLM invocations emit structured
events into the DB.

------------------------------------------------------------------------

## 6. Database Layering (SQLite)

### 6.1 Session/engine rules

-   Create engine **once** per backend process
-   Create session **per request** (FastAPI dependency)
-   Never create sessions inside Streamlit

### 6.2 SQLite performance/quality settings (local)

-   Enable WAL mode for better concurrency (backend + DBeaver reads)
-   Use reasonable pragmas (synchronous, cache_size) as appropriate

### 6.3 Migrations

Until first client: - You may use `SQLModel.metadata.create_all(engine)`
on startup.

Before production: - Introduce migrations (Alembic) and a migration
discipline.

------------------------------------------------------------------------

## 7. Orchestration with LangGraph (OpenClaw-style Context Management)

### 7.1 Why LangGraph + OpenClaw context management

This platform's workflow is a **gated, resumable state machine**:

-   ingest → normalize → propose mappings → validate → detect
    contradictions\
-   **pause for human decisions** (DecisionLocks / ReviewTasks) →
    resume\
-   repeat as new evidence arrives

LangGraph gives us explicit state, cycles, and SQLite persistence (via
`SqliteSaver`), while **OpenClaw-style context management** ensures the
LLM never becomes the source of truth.

**Key idea:** the database "world model" is truth; the LLM is a planner.

### 7.2 Core concept: The Context Packet

We do not pass "chat history" forward.

Instead, each reasoning step compiles a deterministic **ContextPacket**
under a token budget from four "lanes":

1.  **World snapshot** (DB truth): open locks/tasks/contradictions,
    counts, last tool outcomes
2.  **People/Time Anchor** (always-on facts): canonical people IDs,
    payroll totals, timesheet totals, project allocations
3.  **Memory summaries** (compact): key decisions + what's blocked + why
4.  **Evidence pack** (cited): only the most relevant segments/snippets,
    with provenance

### 7.3 Deterministic vs LLM responsibilities

**Deterministic nodes (no LLM):**

-   ensure / derive `thread_id = "{run_id}:{session_id}"`
-   restore/init state from checkpoint
-   load DB snapshot (world model)
-   build anchor lane from verified tables
-   retrieve MemoryDoc summaries (read-only retrieval)
-   retrieve evidence pack (FTS + vector store)
-   context compilation + token budgeting
-   tool execution + logging
-   gate evaluation against DB truth
-   human gate response payload assembly (NEEDS_REVIEW)

**LLM nodes (bounded):**

-   planner: decides the *next tool* or *final response* based on
    ContextPacket
-   summarizer (optional LLM): writes MemoryDoc summaries but must be
    grounded in the DB snapshot + tool results

### 7.4 Required nodes (canonical)

These node definitions are the reference implementation:

1.  `ensure_thread_id`
2.  `restore_or_init_state`
3.  `load_world_snapshot`
4.  `build_anchor_lane` (deterministic)
5.  `memory_retrieve` (deterministic retrieval)
6.  `retrieve_evidence_pack` (deterministic retrieval)
7.  `context_compiler` (deterministic, token budget)
8.  `human_gate` (return NEEDS_REVIEW)
9.  `planner` (LLM)
10. `tool_executor` (1 tool or tiny batch)
11. `gate_evaluator`
12. `summarizer` (writes MemoryDoc)
13. `finalizer`

### 7.5 Wiring rule: Separate Tool Loop from Done/Exit Path

To avoid brittle "half-finished" behavior, the graph's wiring must keep
a clean separation:

-   **Tool Loop path:**\
    `planner (done?=no)` → `tool_executor` → `gate_evaluator` →

    -   if blocked → `human_gate`\
    -   if not blocked → loop back to `load_world_snapshot` to **rebuild
        context** deterministically

-   **Done/Exit path:**\
    `planner (done?=yes)` → `summarizer` → `finalizer`

-   **Human gate also exits cleanly:**\
    `human_gate` → `summarizer` → `finalizer`

### 7.6 Canonical Mermaid (source of truth)

``` mermaid
flowchart TD
  %% SR&ED Agent Orchestration (LangGraph) - OpenClaw-style Context Management
  %% FINAL: Clean separation between Tool Loop and Done/Exit Path

  %% ──────────────────────────────────────────────────────────────
  %% Caller/UI (outside graph)
  %% ──────────────────────────────────────────────────────────────
  subgraph CALLER["Caller/UI Journey (outside LangGraph)"]
    U0([User message])
    A1(["POST /runs/{run_id}/agent/message"])
    U2([UI renders response])
    U3{status = NEEDS_REVIEW?}
    U4(["User reviews locks/tasks/contradictions
in UI"])
    U5(["POST resolve actions
(resolve lock / complete task / attach evidence)"])
    U6([User sends follow-up / Resume])
  end

  %% ──────────────────────────────────────────────────────────────
  %% Persistence
  %% ──────────────────────────────────────────────────────────────
  subgraph PERSIST["Persistence"]
    DB[(SQLite World Model
Run, Files, Segments, People, Timesheets,
Payroll, Aliases, StagingRow, Ledger,
Contradictions, ReviewTasks, DecisionLocks,
MemoryDoc, ToolCallLog, LLMCallLog)]
    CP[(LangGraph Checkpointer
SqliteSaver
thread_id = run_id:session_id
-auto persist after nodes-)]
  end

  %% ──────────────────────────────────────────────────────────────
  %% LangGraph Execution (single invocation)
  %% ──────────────────────────────────────────────────────────────
  subgraph G["LangGraph Execution (single invocation)"]
    S0([start])

    %% --- Identity / Resume ---
    N0["ensure_thread_id
thread_id = '{run_id}:{session_id}'"]
    N1["restore_or_init_state
(load checkpoint or init GraphState)"]

    %% ---- OpenClaw Context Lanes ----
    N2["load_world_snapshot
(open locks/tasks/contradictions,
counts, recent tool outcomes,
last summary pointers)"]
    N3["build_anchor_lane
People/Time Anchor (always-on facts):
- canonical people IDs
- payroll totals
- timesheet totals
- project allocations"]
    N4["memory_retrieve
fetch compact MemoryDoc summaries
(key decisions, what’s blocked, why)"]
    N5["retrieve_evidence_pack
semantic/fts retrieval of only relevant
segments/snippets (top-k + filters)
with provenance/citations"]
    N6["context_compiler (DETERMINISTIC)
Build ContextPacket under token budget:
- DB-backed facts
- anchor constraints
- evidence snippets w/ citations
- open questions
- tool constraints/limits"]

    %% Block-before-plan (OpenClaw style)
    N7{"block_now?
(DecisionLock active OR
missing anchor inputs OR
insufficient evidence coverage)"}
    N8["human_gate
Return NEEDS_REVIEW payload:
- required actions
- missing evidence
- locks/tasks/contradictions
(NO further tool calls)"]

    %% ---- ReAct Planning ----
    N9["planner
Decide next action based on ContextPacket:
A) queue 1 tool
B) ask user question
C) finalize"]
    N10{"done?
(planner chose finalize
or ask-user)
AND no queued tool"}

    %% ---- Tool Execution (separate loop path) ----
    N11["tool_executor
Execute 1 tool (or tiny batch)
Log ToolCallLog + results
Write DB changes"]

    %% After tool: evaluate gates against the DB truth
    N12["gate_evaluator
Query DB for new locks/tasks/
blocking contradictions"]
    N13{"blocked?
(lock active OR blocking contradiction
OR required review task)"}

    %% ---- Exit Path (common) ----
    N14["summarizer
Write MemoryDoc:
- what changed
- what’s pending
- why blocked
- next steps"]
    N15["finalizer
Return payload:
status + answer + refs + next actions"]
    END([end])
  end

  %% ──────────────────────────────────────────────────────────────
  %% Wiring: Graph Flow & ReAct Loop (FINAL)
  %% ──────────────────────────────────────────────────────────────
  U0 --> A1 --> S0
  S0 --> N0 --> N1 --> N2 --> N3 --> N4 --> N5 --> N6 --> N7

  %% 1) Pre-blocked by compiler
  N7 -- "yes" --> N8

  %% 2) Enter ReAct Loop
  N7 -- "no" --> N9 --> N10

  %% 3) Path A: Execute Tools & Re-evaluate Context (OpenClaw Loop)
  N10 -- "no" --> N11 --> N12 --> N13
  N13 -- "no" --> N2
  N13 -- "yes" --> N8

  %% 4) Path B: Done planning successfully
  N10 -- "yes" --> N14

  %% 5) Human Gate converges to Summary
  N8 --> N14

  %% 6) Finalization (Everyone exits here)
  N14 --> N15 --> END

  %% Return to caller journey
  END --> U2 --> U3
  U3 -- "yes" --> U4 --> U5 --> U6 --> A1
  U3 -- "no" --> U2

  %% ──────────────────────────────────────────────────────────────
  %% Persistence side effects (meta)
  %% ──────────────────────────────────────────────────────────────
  N2 -. "reads" .-> DB
  N3 -. "reads" .-> DB
  N5 -. "reads" .-> DB
  N11 -. "writes" .-> DB
  N12 -. "reads" .-> DB
  N14 -. "writes" .-> DB

  N1 -. "persisted by" .-> CP
  N2 -. "persisted by" .-> CP
  N6 -. "persisted by" .-> CP
  N9 -. "persisted by" .-> CP
  N11 -. "persisted by" .-> CP
  N15 -. "persisted by" .-> CP
```

### 7.7 Persistence (checkpoints)

-   Use LangGraph native `SqliteSaver` (**no hand-rolled checkpoint
    tables**).
-   Persist checkpoints in local SQLite.
-   Deterministic `thread_id = "{run_id}:{session_id}"`.
-   Define `GRAPH_STATE_VERSION` and provide a CLI command to
    clear/reset checkpoints per run/session.

------------------------------------------------------------------------

------------------------------------------------------------------------

## 8. Search & VectorStore Refactor (Resolve Brute Force)

### 8.1 Requirements

-   Must support `top_k` semantic retrieval over Segments per run
-   Must not load all embeddings into memory each query
-   Must support filters (run_id, file_id, segment_type)

### 8.2 Strategy

1.  Define a `VectorStore` interface (Strategy Pattern)
2.  Implement **SQLite-backed** indexing for local mode:
    -   Preferred: sqlite vector extension (e.g., sqlite-vec) if
        feasible
    -   Fallback: HNSW/FAISS index persisted to file, with metadata kept
        in SQLite
3.  Keep current hybrid RRF fusion, but swap vector backend

### 8.3 Embedding consistency rule (critical)

-   The embedding model name + dimension must be stored with each
    embedding.
-   The query embedding model must match the stored model.
-   If a mismatch is detected:
    -   trigger re-embed or refuse with actionable error.

------------------------------------------------------------------------

## 9. DuckDB Hardening (CSV Tools)

### 9.1 Threat model (local-only but still risky)

Prompt-injection can convince an agent to call `csv_query()` with SQL
that reads local files (`read_csv_auto('/etc/passwd')`,
`read_parquet('/home/...')`).

### 9.2 Required protections

-   Create DuckDB connection with **external access disabled**
-   Forbid:
    -   `read_*` functions that take paths
    -   `COPY`, `ATTACH`, `INSTALL`, `LOAD`, `PRAGMA`, `EXPORT`
-   Enforce a **SELECT-only** policy:
    -   reject any query not starting with `SELECT` / `WITH`
    -   parse/scan tokens; block prohibited keywords
-   Only allow tables/views that the sandbox registered (e.g., a single
    validated CSV)

### 9.3 Output limits

-   Default row limit (e.g., 200 rows) unless explicitly overridden
-   Default timeout for heavy queries
-   Maximum bytes returned

------------------------------------------------------------------------

## 10. FastAPI Endpoints (Local-Only)

### 10.1 Principles

-   Endpoints map to **services**, not ORM.
-   Responses use **DTOs**, not ORM objects.
-   No auth now; still keep a clean dependency layer for future auth.

### 10.2 Minimum endpoint set for first client

**Health** - `GET /health`

**Runs** - `GET /runs` - `POST /runs` - `GET /runs/{run_id}` -
`POST /runs/{run_id}/select` (optional if you keep "current run"
semantics)

**Files & Ingest** - `POST /runs/{run_id}/files/upload` -
`GET /runs/{run_id}/files` -
`POST /runs/{run_id}/files/{file_id}/process` -
`POST /runs/{run_id}/process_all`

**People & Aliases** - `GET /runs/{run_id}/people` -
`POST /runs/{run_id}/people` - `GET /runs/{run_id}/aliases` -
`POST /runs/{run_id}/aliases/confirm` -
`POST /runs/{run_id}/aliases/resolve`

**Search** - `GET /runs/{run_id}/search?query=...&top_k=...` - returns
hybrid results

**World model / gates** - `GET /runs/{run_id}/tasks?status=open` -
`POST /runs/{run_id}/tasks` -
`GET /runs/{run_id}/contradictions?status=open` -
`POST /runs/{run_id}/contradictions` -
`GET /runs/{run_id}/locks?status=active`

**Finance** - `POST /runs/{run_id}/payroll/extract` -
`POST /runs/{run_id}/payroll/validate` -
`POST /runs/{run_id}/ledger/populate` - `GET /runs/{run_id}/ledger`

**Agent** - `POST /runs/{run_id}/agent/message` (sync) -
`WS /runs/{run_id}/agent/stream` (optional) - both drive the LangGraph
workflow

**Exports** - `GET /runs/{run_id}/export/trace.md` -
`GET /runs/{run_id}/export/ledger.csv`

**Admin (local dev only)** - `GET /admin/db/stats` -
`GET /admin/db/tables/{name}/sample`

------------------------------------------------------------------------

## 11. UI Refactor (Streamlit as Thin Client)

### 11.1 Core rule

Streamlit is allowed to: - capture user input - call API - render API
responses - manage minimal UI state (selected run_id, filters)

Streamlit is **not** allowed to: - open DB sessions - call
ingestion/orchestration directly - import ORM models

### 11.2 UI pages stay, but become API-driven

Keep the same navigation (11 pages). Each page calls the corresponding
endpoint(s).

------------------------------------------------------------------------

## 12. Database Observability (DBeaver + CLI)

### 12.1 DBeaver setup

-   Driver: SQLite
-   File: `data/sred.db`
-   Read/write is allowed in dev; for demos, consider read-only

**Suggested saved queries (add to docs):** - Run summary: files count,
segments count, people count, ledger count - Open contradictions and
tasks by run - Latest agent sessions (LLMCallLog, ToolCallLog) per run -
Embedding coverage: count of segments without embeddings

### 12.2 CLI improvements (high ROI)

-   `sred doctor` (env + DB health + model mismatch checks)
-   `sred db stats` (table sizes, last updated)
-   `sred db sample <table> --limit 50`
-   `sred reindex fts|vectors --run-id X`

------------------------------------------------------------------------

## 13. Testing & CI (Until First Client)

### 13.1 Test pyramid

-   Unit tests:
    -   domain rules
    -   repositories
    -   vector store
    -   SQL safety validator
-   Integration tests:
    -   FastAPI endpoints with test SQLite db
    -   ingest minimal file fixture → segments → search
    -   LangGraph workflow with a fake LLM client
-   E2E smoke test (local):
    -   start backend + UI, run a scripted sequence

### 13.2 CI gates

-   `pytest`
-   format + lint
-   type checks
-   (optional) security scanning for dependencies

------------------------------------------------------------------------

## 14. First Client Definition of Done (MVP Checklist)

A build is "client-ready" when:

### 14.1 Stability

-   UI starts reliably (no mapper collisions)
-   Backend starts reliably, can run with `--reload` in dev
-   Processing a run does not crash on typical PDFs/CSVs

### 14.2 Core workflows

-   Create run
-   Upload evidence files
-   Process files → segments
-   Search (hybrid) works and is fast
-   Aliases can be resolved/confirmed
-   Payroll extract + validate works for a basic input
-   Ledger population produces explainable rows
-   Contradictions and tasks appear and can be resolved
-   Agent can resume with memory and respects gates
-   Trace export works (MD)
-   Ledger export works (CSV)

### 14.3 Safety & audit

-   DuckDB sandbox cannot read arbitrary local files
-   Tool/LLM logs are stored and viewable
-   Provenance fields exist on extracted rows

------------------------------------------------------------------------

## 15. Decision Record Template (add to repo)

Create `docs/adr/ADR-XXXX-title.md` for any decision that impacts
architecture, including: - Orchestration framework changes - Vector
store backend selection - Schema changes - DuckDB policy changes

------------------------------------------------------------------------

## 16. Rules of Engagement (for coding assistants)

1.  Make **small, reviewable changes**
2.  Preserve contracts; introduce new ones deliberately
3.  Add tests for every new boundary
4.  Never "fix by hack" in Streamlit---fix in backend boundaries
5.  Any change that touches "world model" gates requires a regression
    test

------------------------------------------------------------------------

**End of Bible.**

------------------------------------------------------------------------

# 🔒 Mandatory Update: API DTO Enforcement & LangGraph Native Checkpointing

## 17. API Data Transfer Objects (DTOs) --- HARD RULE

To strictly enforce the API ↔ Database boundary:

### 🚫 FastAPI routers MUST NOT:

-   Return SQLModel / SQLAlchemy ORM instances
-   Expose ORM objects directly in responses
-   Depend on lazy-loaded relationships

### ✅ FastAPI routers MUST:

-   Use pure Pydantic request/response DTOs
-   Map ORM → DTO inside the Service layer
-   Perform eager loading (selectinload/joinedload) inside repositories
    when relationships are required
-   Ensure serialization happens only on DTOs

### Why this is non‑negotiable

Returning ORM instances can trigger: - DetachedInstanceError after
UnitOfWork closes - Unintended lazy-loading outside session scope - N+1
query performance regressions - Non-deterministic crashes depending on
execution order

### Acceptance Criteria

-   No router imports SQLModel/Session
-   Tests fail if any router returns ORM models
-   All responses validated via Pydantic schemas under `api/schemas/`

------------------------------------------------------------------------

## 18. LangGraph Checkpointing --- Use Native SqliteSaver

We will NOT hand-roll a custom `graph_checkpoints` table unless
absolutely necessary.

### Required Implementation

-   Use LangGraph's native `SqliteSaver` from
    `langgraph-checkpoint-sqlite`
-   Persist checkpoints inside the existing SQLite database file
    (`data/sred.db`)
-   Use deterministic `thread_id` strategy: `{run_id}:{session_id}`

### Additional Requirements

-   Maintain a `GRAPH_STATE_VERSION` constant
-   Provide CLI command to clear/reset checkpoints per run
-   Ensure checkpoint schema version is logged for migration safety

### Why this is mandatory

Hand-rolled checkpoint systems introduce: - Serialization edge cases -
Tool call replay inconsistencies - Resume bugs - Excess infrastructure
complexity

LangGraph's native saver: - Handles tool-call serialization - Handles
thread persistence - Reduces infrastructure code - Is tested upstream

### Acceptance Criteria

-   Graph resume works after backend restart
-   Tool calls are replay-safe
-   Checkpoints visible via DBeaver in SQLite
-   Integration test validates pause → restart → resume

------------------------------------------------------------------------
