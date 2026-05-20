"""SQLite-backed EventRepository.

Drop-in alternative to InMemoryRepository. Same Protocol, same semantics; the
read-modify-write race for duplicate ids is now resolved by the events PK
instead of an asyncio lock — `INSERT` fails on conflict and we translate
`IntegrityError` to `EventExists`.

Storage uses stdlib `sqlite3` (no new dependency). Async methods hop to a
worker thread via `asyncio.to_thread`; writes are serialised by an
`asyncio.Lock` so a multi-statement `add` (event row + related-entity rows)
runs as one logical transaction without interleaving.

Timestamps are stored as ISO 8601 strings normalised to UTC so lexicographic
order matches chronological order — important for `ORDER BY timestamp`.
`related_entities` is split into its own table (see schema below) so the
"events mentioning entity X" query is index-driven instead of scanning every
row's list.
"""

from __future__ import annotations

import asyncio
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

from app.models import Event
from app.repository import EventExists


_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    type TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    entity TEXT NOT NULL,
    location TEXT NOT NULL,
    normalized_location TEXT NOT NULL,
    confidence REAL NOT NULL,
    description TEXT NOT NULL,
    ingested_at TEXT NOT NULL,
    normalized_entity TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_normalized_entity ON events(normalized_entity);
CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_events_type ON events(type);
CREATE INDEX IF NOT EXISTS idx_events_normalized_location ON events(normalized_location);

CREATE TABLE IF NOT EXISTS event_related_entities (
    event_id TEXT NOT NULL,
    position INTEGER NOT NULL,
    raw TEXT NOT NULL,
    normalized TEXT NOT NULL,
    PRIMARY KEY (event_id, position),
    FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_related_by_normalized ON event_related_entities(normalized, event_id);
"""


_EVENT_COLUMNS = (
    "id, source, type, timestamp, entity, location, normalized_location, "
    "confidence, description, ingested_at, normalized_entity"
)


def _to_iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _from_iso(s: str) -> datetime:
    return datetime.fromisoformat(s)


class SqliteRepository:
    """SQLite-backed event store. Single connection, write-serialised."""

    def __init__(
        self,
        db_path: str | Path = ":memory:",
        *,
        seed: Iterable[Event] = (),
    ) -> None:
        self._db_path = str(db_path)
        # Ensure the parent dir exists for file-backed paths — sqlite3.connect
        # would otherwise fail with "unable to open database file" if it didn't.
        # `:memory:` and `file:...?mode=...` URIs are left alone.
        if self._db_path not in (":memory:", "") and not self._db_path.startswith("file:"):
            Path(self._db_path).expanduser().parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False because asyncio.to_thread will dispatch calls
        # from the loop's worker pool; the asyncio.Lock + sqlite's own internal
        # serialisation keep things safe.
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.executescript(_SCHEMA)
        self._write_lock = asyncio.Lock()

        for event in seed:
            self._add_sync(event)

    def close(self) -> None:
        self._conn.close()

    async def add(self, event: Event) -> Event:
        async with self._write_lock:
            return await asyncio.to_thread(self._add_sync, event)

    def _add_sync(self, event: Event) -> Event:
        try:
            self._conn.execute(
                f"INSERT INTO events ({_EVENT_COLUMNS}) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    event.id,
                    event.source,
                    event.type,
                    _to_iso(event.timestamp),
                    event.entity,
                    event.location,
                    event.location.strip().lower(),
                    event.confidence,
                    event.description,
                    _to_iso(event.ingested_at),
                    event.normalized_entity,
                ),
            )
            for position, related in enumerate(event.related_entities):
                self._conn.execute(
                    "INSERT INTO event_related_entities "
                    "(event_id, position, raw, normalized) VALUES (?,?,?,?)",
                    (event.id, position, related, related.strip().lower()),
                )
            self._conn.commit()
        except sqlite3.IntegrityError as exc:
            # PK conflict on events.id — caller treats this as "duplicate".
            # (event_related_entities PK uses event_id + a loop-index position,
            # so a conflict there can only happen if events.id already conflicted.)
            self._conn.rollback()
            raise EventExists(event.id) from exc
        return event

    async def get(self, event_id: str) -> Optional[Event]:
        return await asyncio.to_thread(self._get_sync, event_id)

    def _get_sync(self, event_id: str) -> Optional[Event]:
        row = self._conn.execute(
            f"SELECT {_EVENT_COLUMNS} FROM events WHERE id = ?", (event_id,)
        ).fetchone()
        if row is None:
            return None
        return self._hydrate_many([row])[0]

    async def list(self, *, limit: int, offset: int) -> list[Event]:
        return await asyncio.to_thread(self._list_sync, limit, offset)

    def _list_sync(self, limit: int, offset: int) -> list[Event]:
        rows = self._conn.execute(
            f"SELECT {_EVENT_COLUMNS} FROM events "
            "ORDER BY timestamp DESC, id DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
        return self._hydrate_many(rows)

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
        return await asyncio.to_thread(
            self._search_sync, type, entity, location, min_confidence, limit, offset
        )

    def _search_sync(
        self,
        type_: Optional[str],
        entity: Optional[str],
        location: Optional[str],
        min_confidence: Optional[float],
        limit: int,
        offset: int,
    ) -> list[Event]:
        clauses: list[str] = []
        params: list = []
        if type_ is not None:
            clauses.append("type = ?")
            params.append(type_)
        if entity is not None:
            clauses.append("normalized_entity = ?")
            params.append(entity.strip().lower())
        if location is not None:
            clauses.append("normalized_location = ?")
            params.append(location.strip().lower())
        if min_confidence is not None:
            clauses.append("confidence >= ?")
            params.append(min_confidence)

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = (
            f"SELECT {_EVENT_COLUMNS} FROM events {where} "
            "ORDER BY timestamp DESC, id DESC LIMIT ? OFFSET ?"
        )
        params.extend([limit, offset])
        rows = self._conn.execute(sql, params).fetchall()
        return self._hydrate_many(rows)

    async def events_for_entity(self, entity_id: str) -> list[Event]:
        return await asyncio.to_thread(self._events_for_entity_sync, entity_id)

    def _events_for_entity_sync(self, entity_id: str) -> list[Event]:
        target = entity_id.strip().lower()
        rows = self._conn.execute(
            f"SELECT {_EVENT_COLUMNS} FROM events "
            "WHERE normalized_entity = ? "
            "   OR id IN (SELECT event_id FROM event_related_entities WHERE normalized = ?)",
            (target, target),
        ).fetchall()
        return self._hydrate_many(rows)

    async def all_entities(self) -> set[str]:
        return await asyncio.to_thread(self._all_entities_sync)

    def _all_entities_sync(self) -> set[str]:
        rows = self._conn.execute(
            "SELECT normalized_entity AS e FROM events "
            "UNION SELECT normalized AS e FROM event_related_entities"
        ).fetchall()
        return {row["e"] for row in rows}

    def _hydrate_many(self, rows: list[sqlite3.Row]) -> list[Event]:
        if not rows:
            return []
        ids = [r["id"] for r in rows]
        placeholders = ",".join("?" * len(ids))
        rel_rows = self._conn.execute(
            "SELECT event_id, raw FROM event_related_entities "
            f"WHERE event_id IN ({placeholders}) "
            "ORDER BY event_id, position",
            ids,
        ).fetchall()
        rel_by_event: dict[str, list[str]] = {}
        for rr in rel_rows:
            rel_by_event.setdefault(rr["event_id"], []).append(rr["raw"])
        return [self._row_to_event(r, rel_by_event.get(r["id"], [])) for r in rows]

    @staticmethod
    def _row_to_event(row: sqlite3.Row, related: list[str]) -> Event:
        return Event(
            id=row["id"],
            source=row["source"],
            type=row["type"],
            timestamp=_from_iso(row["timestamp"]),
            entity=row["entity"],
            location=row["location"],
            confidence=row["confidence"],
            description=row["description"],
            related_entities=related,
            ingested_at=_from_iso(row["ingested_at"]),
            normalized_entity=row["normalized_entity"],
        )
