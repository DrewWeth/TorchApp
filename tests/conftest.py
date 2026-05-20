"""Shared pytest fixtures.

The `repo` fixture is parameterized across both repository implementations so
every test that depends on it (directly or via `client`) runs against both
InMemory and SQLite. This is how we prove the `EventRepository` swap works.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.normalize import normalize
from app.repository import EventRepository, InMemoryRepository
from app.sqlite_repository import SqliteRepository


SEED_RAW = [
    {
        "id": "evt-101",
        "source": "sensor-feed",
        "type": "movement",
        "timestamp": "2026-01-01T10:00:00Z",
        "entity": "unit-alpha",
        "location": "Region-A",
        "confidence": 0.92,
        "description": "Unusual movement pattern detected near checkpoint",
        "related_entities": ["unit-bravo"],
    },
    {
        "id": "evt-102",
        "source": "analyst-note",
        "type": "observation",
        "timestamp": "2026-01-01T10:05:00Z",
        "entity": "unit-bravo",
        "location": "Region-A",
        "confidence": 0.74,
        "description": "Analyst observed possible coordination with unit-alpha",
        "related_entities": ["unit-alpha"],
    },
    {
        "id": "evt-103",
        "source": "signal-feed",
        "type": "signal",
        "timestamp": "2026-01-01T10:12:00Z",
        "entity": "unknown-signal-77",
        "location": "Region-B",
        "confidence": 0.66,
        "description": "Signal anomaly detected",
        "related_entities": [],
    },
    {
        "id": "evt-104",
        "source": "alert-engine",
        "type": "alert",
        "timestamp": "2026-01-01T10:20:00Z",
        "entity": "unit-alpha",
        "location": "Region-A",
        "confidence": 0.89,
        "description": "Potential escalation based on movement and analyst observation",
        "related_entities": ["unit-bravo", "unknown-signal-77"],
    },
]

FIXED_NOW = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture(params=["memory", "sqlite"])
def repo(request) -> EventRepository:
    seeded = [normalize(r, now=FIXED_NOW) for r in SEED_RAW]
    if request.param == "memory":
        return InMemoryRepository(seed=seeded)
    sqlite_repo = SqliteRepository(db_path=":memory:", seed=seeded)
    request.addfinalizer(sqlite_repo.close)
    return sqlite_repo


@pytest.fixture
def client(repo: EventRepository) -> TestClient:
    return TestClient(create_app(repo))
