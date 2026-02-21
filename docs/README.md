# docs/

This directory contains the authoritative architecture and coding-assistant guidance for the SR&ED Automation Platform.

## Files

### `REFRACTORING_BIBLE.md`
The **source of truth** for every architectural decision until first client delivery.

**Read this before writing any code.** It defines:
- North Star and constraints
- Target architecture (FastAPI + LangGraph + Repository/UoW)
- Design patterns enforced (Repository, UoW, Command, Strategy, Adapter, Factory)
- LangGraph orchestration model (OpenClaw-style context management)
- DuckDB hardening requirements
- Database session rules
- VectorStore refactor strategy
- First-client definition of done

### `CODING_ASSISTANT_PROMPT_PACK.md`
A phased series of prompts that guide AI coding assistants through the refactor in safe, reviewable increments.

Use this to stage work: each Phase builds on the previous and keeps changes small and testable.

## How to use

1. Read `REFRACTORING_BIBLE.md` in full before starting any work.
2. Use `CODING_ASSISTANT_PROMPT_PACK.md` to pick the next Phase to implement.
3. Log significant architectural decisions as ADRs in `docs/adr/ADR-XXXX-title.md`.
