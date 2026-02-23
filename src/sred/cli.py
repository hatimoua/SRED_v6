import os
import sys
import typer
from pathlib import Path
from sred.config import settings
from sred.logging import logger, get_run_id

app = typer.Typer(no_args_is_help=True)

@app.callback()
def main():
    """
    SR&ED Automation CLI.
    """
    pass

@app.command(name="doctor")
def doctor():
    """
    Check system configuration and environment health.
    """
    logger.info("Running doctor check...")

    failures: list[str] = []
    passed = 0

    print("\n🩺 SRED Automation Doctor\n")

    # ── Check 1: Environment / Interpreter ──────────────────────────────────
    print("[Environment]")
    print(f"  Python: {sys.version.split()[0]}")
    print(f"  Prefix: {sys.prefix}")
    print(f"  Run ID: {get_run_id()}")
    passed += 1

    # ── Check 2: OpenAI API Key ──────────────────────────────────────────────
    print("\n[Configuration]")
    api_key_ok = bool(
        settings.OPENAI_API_KEY and settings.OPENAI_API_KEY.get_secret_value()
    )
    if api_key_ok:
        print("  OPENAI_API_KEY:              ✅ Set")
        passed += 1
    else:
        print("  OPENAI_API_KEY:              ❌ Missing")
        failures.append("OPENAI_API_KEY is not set — add it to .env")

    print(f"  OPENAI_MODEL_AGENT:          {settings.OPENAI_MODEL_AGENT}")
    print(f"  OPENAI_MODEL_VISION:         {settings.OPENAI_MODEL_VISION}")
    print(f"  OPENAI_MODEL_STRUCTURED:     {settings.OPENAI_MODEL_STRUCTURED}")
    print(f"  PAYROLL_MISMATCH_THRESHOLD:  {settings.PAYROLL_MISMATCH_THRESHOLD}")

    # ── Check 3: Embedding model non-empty ──────────────────────────────────
    DEFAULT_EMBEDDING_MODEL = "text-embedding-3-large"
    embedding_model = settings.OPENAI_EMBEDDING_MODEL
    if embedding_model:
        note = "" if embedding_model == DEFAULT_EMBEDDING_MODEL else f" (non-default: {embedding_model!r})"
        print(f"  OPENAI_EMBEDDING_MODEL:      ✅ {embedding_model}{note}")
        passed += 1
    else:
        print("  OPENAI_EMBEDDING_MODEL:      ❌ Empty")
        failures.append("OPENAI_EMBEDDING_MODEL is blank — check config.py default")

    # ── Check 4: Data directory ──────────────────────────────────────────────
    print("\n[Data Directory]")
    data_dir = Path("data")
    if data_dir.exists() and data_dir.is_dir():
        print(f"  data/                        ✅ Found: {data_dir.absolute()}")
        passed += 1
    else:
        print(f"  data/                        ❌ Missing: {data_dir.absolute()}")
        failures.append(f"data/ directory not found at {data_dir.absolute()} — run `mkdir data`")

    # ── Check 5: DB file / directory writability ─────────────────────────────
    print("\n[Database]")
    db_file = Path("data/sred.db")
    if db_file.exists():
        if os.access(db_file, os.W_OK):
            print(f"  data/sred.db                 ✅ Exists and writable")
            passed += 1
        else:
            print(f"  data/sred.db                 ❌ Exists but NOT writable")
            failures.append(f"data/sred.db exists but is not writable — check file permissions")
    elif data_dir.exists():
        if os.access(data_dir, os.W_OK):
            print(f"  data/sred.db                 ✅ Does not exist yet; data/ is writable (db init can create it)")
            passed += 1
        else:
            print(f"  data/sred.db                 ❌ data/ directory is not writable")
            failures.append("data/ directory is not writable — db init cannot create sred.db")
    else:
        # data dir missing — already captured above; skip this check
        print(f"  data/sred.db                 ⚠️  Skipped (data/ missing)")

    # ── Summary ──────────────────────────────────────────────────────────────
    total = passed + len(failures)
    print(f"\n{'─' * 50}")
    if failures:
        print(f"Result: {passed}/{total} checks passed\n")
        for msg in failures:
            print(f"  ❌ {msg}")
        print()
        raise typer.Exit(code=1)
    else:
        print(f"Result: {passed}/{total} checks passed — all good ✅")
        print()


db_app = typer.Typer(help="Database management commands.")
app.add_typer(db_app, name="db")

@db_app.command("init")
def init():
    """Initialize the database tables."""
    from sred.db import init_db
    from sred.search import setup_fts
    try:
        init_db()
        setup_fts()
        logger.info("Database initialized successfully.")
        print("✅ Database initialized.")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        print(f"❌ Failed: {e}")
        raise typer.Exit(code=1)

@db_app.command("reindex")
def reindex():
    """Rebuild FTS5 search index."""
    from sred.search import reindex_all
    try:
        reindex_all()
        print("✅ Search index rebuilt.")
    except Exception as e:
        logger.error(f"Reindex failed: {e}")
        print(f"❌ Failed: {e}")
        raise typer.Exit(code=1)

@db_app.command("search")
def search(query: str):
    """Search segments using FTS5."""
    from sred.search import search_segments
    results = search_segments(query)
    if not results:
        print("No results found.")
        return
        
    print(f"Found {len(results)} results:")
    for i, (id, snippet) in enumerate(results, 1):
        print(f"{i}. [ID {id}] {snippet}")

graph_app = typer.Typer(help="LangGraph checkpoint management.")
app.add_typer(graph_app, name="graph")

@graph_app.command("reset")
def graph_reset(
    run_id: int | None = typer.Option(None, help="Clear checkpoints for this run ID"),
    session_id: str | None = typer.Option(None, help="Clear checkpoints for this session (requires --run-id)"),
    all_: bool = typer.Option(False, "--all", help="Clear ALL checkpoints"),
):
    """Clear LangGraph checkpoints."""
    from sred.orchestration.checkpointer import clear_checkpoints

    if not all_ and run_id is None:
        print("❌ Provide --run-id, --run-id + --session-id, or --all")
        raise typer.Exit(code=1)

    if session_id is not None and run_id is None:
        print("❌ --session-id requires --run-id")
        raise typer.Exit(code=1)

    deleted = clear_checkpoints(run_id=run_id, session_id=session_id)

    if run_id and session_id:
        scope = f"thread {run_id}:{session_id}"
    elif run_id:
        scope = f"run {run_id}"
    else:
        scope = "all checkpoints"

    print(f"✅ Cleared {scope} ({deleted} rows deleted)")

if __name__ == "__main__":
    app()
