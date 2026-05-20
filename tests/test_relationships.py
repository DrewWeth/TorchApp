"""Pure-function tests for relationship logic.

The repository methods are async; we drive them with asyncio.run() so these
tests stay framework-free (no pytest-asyncio dependency).
"""

from __future__ import annotations

import asyncio

from app.relationships import build_relationships
from app.repository import InMemoryRepository


def test_build_relationships_unit_alpha(repo: InMemoryRepository):
    """unit-alpha is primary on evt-101 & evt-104, and is related on evt-102."""
    own = asyncio.run(repo.events_for_entity("unit-alpha"))
    all_events = asyncio.run(repo.list(limit=1000, offset=0))

    result = build_relationships(
        "unit-alpha", own, all_events, window_seconds=30 * 60
    )

    assert result.entity == "unit-alpha"
    assert {e.id for e in result.direct_events} == {"evt-101", "evt-104"}
    assert {e.id for e in result.mentioned_in} == {"evt-102"}

    assert "unit-bravo" in result.co_occurring_entities
    assert "unknown-signal-77" in result.co_occurring_entities
    assert "unit-alpha" not in result.co_occurring_entities


def test_temporal_neighbours_include_signal(repo: InMemoryRepository):
    """evt-103 (10:12, Region-B) is within 30min of unit-alpha events but in a
    different region — appears as a temporal neighbour with same_location=False."""
    own = asyncio.run(repo.events_for_entity("unit-alpha"))
    all_events = asyncio.run(repo.list(limit=1000, offset=0))

    result = build_relationships(
        "unit-alpha", own, all_events, window_seconds=30 * 60
    )
    neighbour_ids = {n.event_id for n in result.temporal_neighbors}
    assert "evt-103" in neighbour_ids
    sig = next(n for n in result.temporal_neighbors if n.event_id == "evt-103")
    assert sig.same_location is False
    assert sig.delta_seconds <= 30 * 60


def test_temporal_window_excludes_far_events(repo: InMemoryRepository):
    """A 1-second window admits no neighbours."""
    own = asyncio.run(repo.events_for_entity("unit-alpha"))
    all_events = asyncio.run(repo.list(limit=1000, offset=0))

    result = build_relationships("unit-alpha", own, all_events, window_seconds=1)
    assert result.temporal_neighbors == []
