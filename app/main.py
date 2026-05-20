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
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from app.normalize import normalize
from app.repository import EventRepository, InMemoryRepository
from app.routers import entities, events

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s"
)
logger = logging.getLogger("app")

SEED_PATH = Path(__file__).parent.parent / "data" / "seed.json"


def _load_seed() -> InMemoryRepository:
    if not SEED_PATH.exists():
        logger.info("no seed file at %s; starting empty", SEED_PATH)
        return InMemoryRepository()

    raw_events = json.loads(SEED_PATH.read_text())
    seeded = [normalize(r) for r in raw_events]
    logger.info("seeded %d events from %s", len(seeded), SEED_PATH)
    return InMemoryRepository(seed=seeded)


@asynccontextmanager
async def lifespan(app: FastAPI):
    repo = _load_seed()
    app.state.repo = repo
    app.dependency_overrides[events.get_repo] = lambda: repo
    yield
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
