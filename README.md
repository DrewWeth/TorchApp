# Torch Events Service

FastAPI service for the Torch.AI backend exercise. Ingests operational events, normalizes them, exposes search + relationship queries.

## Scripts

Workflows go through [taskipy](https://github.com/taskipy/taskipy) — the npm-scripts equivalent for Python. Tasks live in `pyproject.toml` under `[tool.taskipy.tasks]`.

**First-time setup** (only thing you run by hand):

```bash
python3 bootstrap.py
```

This creates `.venv/` and installs the project + dev deps including `taskipy`.

**After that**, all commands are tasks:

```bash
.venv/bin/task setup    # re-install deps (run after editing pyproject.toml)
.venv/bin/task dev      # uvicorn with auto-reload on http://127.0.0.1:8000
.venv/bin/task test     # pytest
```

Or activate the venv (`source .venv/bin/activate`) and drop the prefix: `task dev`.

> **Windows note.** Tasks hardcode the POSIX `.venv/bin/python` path. On Windows, either activate the venv first (`.venv\Scripts\activate`) and edit `pyproject.toml` to drop the prefix, or run modules directly: `.venv\Scripts\python -m pytest`.

Swagger UI lives at http://127.0.0.1:8000/docs when the dev server is running. The service seeds itself from `data/seed.json` on startup.

## Running in Docker

```bash
docker build -t torch-events .
docker run --rm -p 8000:8000 torch-events
```

## Troubleshooting

### `[Errno 48] Address already in use`

The port is already bound by another process. Find and kill it:

```
lsof -i :8000
kill -9 <PID>
```

## API

| Method | Path | Notes |
| --- | --- | --- |
| `GET` | `/events?limit=&offset=` | List all events, newest first. Limit defaults to 100, max 1000. |
| `GET` | `/events/{id}` | 404 if not found. |
| `GET` | `/events/search?type=&entity=&location=&min_confidence=` | All filters optional, ANDed together. |
| `POST` | `/events` | 201 on success, 409 on duplicate id, 422 on validation failure. |
| `GET` | `/entities/{entity_id}/relationships?window_minutes=30` | Structured relationship view; 404 if entity not seen. |
| `GET` | `/healthz` | Liveness probe. |

### Example requests

```bash
curl http://127.0.0.1:8000/events | jq

curl 'http://127.0.0.1:8000/events/search?type=movement&min_confidence=0.9'

curl http://127.0.0.1:8000/entities/unit-alpha/relationships | jq

curl -X POST http://127.0.0.1:8000/events \
  -H 'content-type: application/json' \
  -d '{
    "id":"evt-999","source":"sensor-feed","type":"movement",
    "timestamp":"2026-02-01T10:00:00Z","entity":"unit-delta",
    "location":"Region-C","confidence":0.5,
    "description":"new event","related_entities":[]
  }'
```

### Relationship response shape

```json
{
  "entity": "unit-alpha",
  "direct_events":  [/* events where entity == unit-alpha */],
  "mentioned_in":   [/* events where unit-alpha ∈ related_entities */],
  "co_occurring_entities": ["unit-bravo", "unknown-signal-77"],
  "temporal_neighbors": [
    {"event_id":"evt-103","delta_seconds":720,"same_location":false}
  ]
}
```

## Design

**Layering.** `normalize.py` and `relationships.py` are pure functions. The routers are thin: parse → call repo + service → return. `repository.py` defines a `Protocol`, so the I/O layer is one swap away from SQLite or Postgres. This is also the seam a Kafka/NiFi consumer would plug into.

**Storage.** Two implementations of `EventRepository` ship: `InMemoryRepository` (default; process-local, ephemeral, fast) and `SqliteRepository` (file- or in-memory-backed, durable). Set `TORCH_EVENTS_DB=/path/to/events.db` to use SQLite — anything else (unset/empty) keeps in-memory. Use `:memory:` for an isolated SQLite instance. The test suite runs every API + relationship test against both impls via a parameterized fixture, which is how we prove the swap is real. A Postgres impl would slot in the same way.

**Normalization.** Validates with Pydantic (rejects naive timestamps and out-of-range confidence), strips whitespace on `related_entities`, stores both `entity` (preserved) and `normalized_entity` (stripped + lowercased) so queries are case-insensitive without rewriting source data. Stamps `ingested_at` at processing time.

**Unknown event types.** The spec uses five types but new sources will add more. `type` is a free string at the schema layer; unknown values log a warning rather than reject ingest, so a new source ships without code changes.

**Relationships.** The endpoint splits the answer into three parts so the analyst sees structure: events where the entity is primary, events where they were mentioned by someone else, and co-occurring entities. The `temporal_neighbors` block adds events near in time (default ±30 min) with a `same_location` flag.

**Concurrency.** `POST /events` does a read-modify-write. `InMemoryRepository` serialises writes with an `asyncio.Lock`. `SqliteRepository` pushes the check down to the `events.id` primary key — `INSERT` fails on conflict and the repo translates `IntegrityError` to `EventExists`. A multi-statement `add` (event row + related-entity rows) is still wrapped by an `asyncio.Lock` so the two-table write commits atomically without interleaving.

## Assumptions

- The given dataset is the contract. New event types are accepted with a log warning rather than schema migration.
- Entity identity is "string equality after strip + lowercase". A real system would resolve aliases via an entity-resolution service.
- A single uvicorn process is sufficient for the exercise scale. Multi-worker deployment requires a shared store (see Storage above).
- `temporal_neighbors` uses absolute time delta; no per-event direction (before/after). Easy to add.

## Production considerations & follow-ups

- **Scale to millions/day.** Move to Postgres with `(entity)` and `(location, timestamp)` indexes plus a join table for related_entities so traversal does not scan all events. At higher scale, a graph DB (Neo4j) for the relationship endpoint, or precomputed materialised views.
- **Kafka / NiFi ingest.** `normalize()` is framework-free and can be called from a consumer worker that writes to the same repository. Add idempotency on `id` to absorb at-least-once redelivery.
- **Observability.** Structured logging is configured in `app/main.py`; add request-ID middleware, `/metrics` for Prometheus, and OpenTelemetry spans around the relationship query (the most expensive path).
- **Security.** Out of scope here. In production: OAuth2/JWT at the gateway, scoped roles (analyst-read vs ingestor-write), audit logging on `POST`.
- **Pagination.** Current impl uses offset/limit. Cursor pagination on `(timestamp, id)` is more correct at scale.
- **Schema evolution.** Pydantic + lenient `type` field gets us forward-compatible. For bigger changes, version the API (`/v1/`) and dual-write during migration.

## What I would build next

1. Cursor pagination on `/events`.
2. Request-ID logging middleware.
3. Property-based tests on `normalize` with Hypothesis.
4. A Kafka consumer worker reusing `normalize()` and `repo.add()`.
5. Postgres implementation of `EventRepository` (the next step up from SQLite for multi-worker deployments).


# Development Notes

## Race Condition on Read-Modify-Write

To avoid race conditions on read-modify-write, the current InMemory implementation uses asyncio's single-process-lock to reject concurrent writes. To do this at scale with multiple workers, this single process lock should move down to the database using row-level lock in Postgres (eg `SELECT ... FOR UPDATE`). Catching `IntegrityError` at the handler level.

## DB Tables and Indexes

Generally, indexes for query optimizations should be driven by query patterns, using EXPLAIN to understand where indexes would be worth trade offs. 

Below are intended implementation SQL tables.

### Table `events`
 
Primary store for normalized event log.

 - Primary Unique key on ID.
 - Index on `normalized_entity`
 - Possible index on confidence if most queries are around a threshold, for example >= 0.7


### Table `event_related_entities`

for many-to-many between `event id` and `related_entity`. For queries: "give me all events mentioning entity x".

- Index `(related_entity, event_id)` for "by entity first, then newest first".
