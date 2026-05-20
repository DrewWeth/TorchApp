"""FastAPI app entry point.

Loads seed events from data/seed.json on startup, wires the in-memory
repository into both routers via FastAPI's dependency override.

Run locally:
    uvicorn app.main:app --reload
Swagger UI: http://127.0.0.1:8000/docs
"""

from __future__ import annotations

import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from app.normalize import normalize
from app.repository import EventExists, EventRepository, InMemoryRepository
from app.routers import entities, events
from app.sqlite_repository import SqliteRepository

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s"
)
logger = logging.getLogger("app")

SEED_PATH = Path(__file__).parent.parent / "data" / "seed.json"
DB_ENV_VAR = "TORCH_EVENTS_DB"


def _seed_events() -> list:
    if not SEED_PATH.exists():
        logger.info("no seed file at %s; starting empty", SEED_PATH)
        return []
    raw_events = json.loads(SEED_PATH.read_text())
    return [normalize(r) for r in raw_events]


def _build_repo() -> EventRepository:
    """Pick an EventRepository impl based on the TORCH_EVENTS_DB env var.

    Unset or empty → InMemoryRepository (default; process-local, ephemeral).
    Anything else → SqliteRepository at that path. Use ":memory:" for an
    isolated in-process SQLite instance.
    """
    seeded = _seed_events()
    db_path = os.environ.get(DB_ENV_VAR, "").strip()

    if not db_path:
        logger.info("using in-memory repo; seeded %d events", len(seeded))
        return InMemoryRepository(seed=seeded)

    # SQLite seeding is idempotent: if the file already has these ids (warm
    # restart), skip them instead of crashing.
    repo = SqliteRepository(db_path=db_path)
    inserted = 0
    for event in seeded:
        try:
            repo._add_sync(event)
            inserted += 1
        except EventExists:
            pass
    logger.info(
        "using sqlite repo at %s; inserted %d/%d seed events",
        db_path,
        inserted,
        len(seeded),
    )
    return repo


@asynccontextmanager
async def lifespan(app: FastAPI):
    repo = _build_repo()
    app.state.repo = repo
    app.dependency_overrides[events.get_repo] = lambda: repo
    try:
        yield
    finally:
        if hasattr(repo, "close"):
            repo.close()
        app.dependency_overrides.clear()


app = FastAPI(
    title="Torch Events Service",
    description="Operational event ingest, query, and relationship API.",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(events.router)
app.include_router(entities.router)


@app.get("/healthz", tags=["meta"])
async def healthz() -> dict[str, str]:
    """Liveness probe for k8s / load balancers."""
    return {"status": "ok"}


def create_app(repo: EventRepository) -> FastAPI:
    """Test helper: build an app instance bound to a caller-supplied repo.

    Avoids reading the seed file in unit tests and lets each test get a
    fresh, isolated repository.
    """
    test_app = FastAPI(title="Torch Events Service (test)")
    test_app.include_router(events.router)
    test_app.include_router(entities.router)
    test_app.dependency_overrides[events.get_repo] = lambda: repo

    @test_app.get("/healthz")
    async def _healthz() -> dict[str, str]:
        return {"status": "ok"}

    return test_app
