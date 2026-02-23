"""FastAPI application factory."""
from __future__ import annotations
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlmodel import SQLModel
from sred.domain.exceptions import NotFoundError, ConflictError


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        from sred.infra.db.engine import engine  # triggers WAL pragma + mapper registration
        from sred.infra.db.schema_compat import ensure_schema_compat
        SQLModel.metadata.create_all(engine)
        ensure_schema_compat(engine)
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
    from sred.api.routers.people import router as people_router
    from sred.api.routers.dashboard import router as dashboard_router
    from sred.api.routers.logs import router as logs_router
    from sred.api.routers.search import router as search_router
    from sred.api.routers.tasks import router as tasks_router
    from sred.api.routers.payroll import router as payroll_router
    from sred.api.routers.ledger import router as ledger_router
    from sred.api.routers.csv import router as csv_router

    app.include_router(runs_router)
    app.include_router(files_router)
    app.include_router(ingest_router)
    app.include_router(people_router)
    app.include_router(dashboard_router)
    app.include_router(logs_router)
    app.include_router(search_router)
    app.include_router(tasks_router)
    app.include_router(payroll_router)
    app.include_router(ledger_router)
    app.include_router(csv_router)

    @app.exception_handler(NotFoundError)
    def _not_found(request: Request, exc: NotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": exc.message})

    @app.exception_handler(ConflictError)
    def _conflict(request: Request, exc: ConflictError) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": exc.message})

    @app.get("/health", tags=["ops"])
    def health() -> dict:
        return {"status": "ok"}

    return app
