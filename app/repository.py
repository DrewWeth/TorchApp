"""Storage abstraction for events.

`EventRepository` is the Protocol that handlers depend on. `InMemoryRepository`
is the shipped implementation — fast, dependency-free, and good enough for the
exercise. A SQLAlchemy/SQLite or Postgres impl would slot in behind the same
interface; the swap point is `app.main.get_repository`.

Concurrency: POST does a read-modify-write (existence check, then insert) which
races under concurrent requests. `_lock` serialises writes; reads are lock-free
because dict reads are atomic under the GIL for single ops.
"""

from __future__ import annotations

import asyncio
from typing import Iterable, Optional, Protocol

from app.models import Event


class EventExists(Exception):
    """Raised when inserting an event whose id is already stored."""


class EventRepository(Protocol):
    async def add(self, event: Event) -> Event: ...
    async def get(self, event_id: str) -> Optional[Event]: ...
    async def list(self, *, limit: int, offset: int) -> list[Event]: ...
    async def search(
        self,
        *,
        type: Optional[str] = None,
        entity: Optional[str] = None,
        location: Optional[str] = None,
        min_confidence: Optional[float] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Event]: ...
    async def events_for_entity(self, entity_id: str) -> list[Event]: ...
    async def all_entities(self) -> set[str]: ...


class InMemoryRepository:
    """Dict-backed store with an asyncio write lock."""

    def __init__(self, seed: Iterable[Event] = ()) -> None:
        self._by_id: dict[str, Event] = {e.id: e for e in seed}
        self._lock = asyncio.Lock()

    async def add(self, event: Event) -> Event:
        async with self._lock:
            if event.id in self._by_id:
                raise EventExists(event.id)
            self._by_id[event.id] = event
            return event

    async def get(self, event_id: str) -> Optional[Event]:
        return self._by_id.get(event_id)

    async def list(self, *, limit: int, offset: int) -> list[Event]:
        # Sort by timestamp desc so the newest events come first — the typical
        # analyst view. Stable for ties via id.
        ordered = sorted(
            self._by_id.values(), key=lambda e: (e.timestamp, e.id), reverse=True
        )
        return ordered[offset : offset + limit]

    async def search(
        self,
        *,
        type: Optional[str] = None,
        entity: Optional[str] = None,
        location: Optional[str] = None,
        min_confidence: Optional[float] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Event]:
        entity_norm = entity.strip().lower() if entity else None
        location_norm = location.strip().lower() if location else None

        def matches(e: Event) -> bool:
            if type is not None and e.type != type:
                return False
            if entity_norm is not None and e.normalized_entity != entity_norm:
                return False
            if location_norm is not None and e.location.strip().lower() != location_norm:
                return False
            if min_confidence is not None and e.confidence < min_confidence:
                return False
            return True

        ordered = sorted(
            (e for e in self._by_id.values() if matches(e)),
            key=lambda e: (e.timestamp, e.id),
            reverse=True,
        )
        return ordered[offset : offset + limit]

    async def events_for_entity(self, entity_id: str) -> list[Event]:
        # An entity is "associated" with an event if it is the primary entity
        # OR it appears in related_entities. We compare on the normalized
        # (stripped+lowercased) form so callers don't need to know our casing.
        target = entity_id.strip().lower()
        return [
            e
            for e in self._by_id.values()
            if e.normalized_entity == target
            or target in {r.strip().lower() for r in e.related_entities}
        ]

    async def all_entities(self) -> set[str]:
        out: set[str] = set()
        for e in self._by_id.values():
            out.add(e.normalized_entity)
            out.update(r.strip().lower() for r in e.related_entities)
        return out
