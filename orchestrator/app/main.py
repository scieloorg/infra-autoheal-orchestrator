from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import get_settings
from app.dependencies import get_event_store, get_state_store
from app.logging_config import configure_logging
from app.routes.alertmanager import router as alertmanager_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)
    get_event_store()
    get_state_store()
    yield


app = FastAPI(
    title="Infra Autoheal Orchestrator",
    version="0.1.0",
    lifespan=lifespan,
)
app.include_router(alertmanager_router)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}
