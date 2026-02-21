"""FastAPI application factory."""
from __future__ import annotations
from contextlib import asynccontextmanager
from fastapi import FastAPI
from sqlmodel import SQLModel


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        from sred.infra.db.engine import engine  # triggers WAL pragma + mapper registration
        SQLModel.metadata.create_all(engine)
        from sred.search.fts import setup_fts
        setup_fts()
        yield

    app = FastAPI(
        title="SR&ED Automation API",
        version="0.2.0",
        lifespan=lifespan,
    )

    # Import routers inside create_app() to avoid circular imports at module load time
    from sred.api.routers.runs import router as runs_router
    from sred.api.routers.files import router as files_router
    from sred.api.routers.ingest import router as ingest_router

    app.include_router(runs_router)
    app.include_router(files_router)
    app.include_router(ingest_router)

    @app.get("/health", tags=["ops"])
    def health() -> dict:
        return {"status": "ok"}

    return app
