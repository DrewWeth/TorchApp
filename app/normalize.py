"""Pure-function normalization: raw dict → Event.

Lives outside the HTTP layer so the same code path can be driven by a Kafka
consumer, a NiFi processor, a CLI loader, or the POST handler.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from app.models import KNOWN_EVENT_TYPES, Event, EventIn

logger = logging.getLogger(__name__)


def normalize(raw: dict[str, Any] | EventIn, *, now: datetime | None = None) -> Event:
    """Validate + enrich a raw event payload.

    Accepts either a dict (from JSON ingest) or a parsed EventIn.
    Adds:
      - ingested_at: server wall-clock at processing time (UTC)
      - normalized_entity: stripped + lowercased copy of entity, used for query
    Logs (does not reject) unknown event types so new sources don't break ingest.
    """
    event_in = raw if isinstance(raw, EventIn) else EventIn.model_validate(raw)

    if event_in.type not in KNOWN_EVENT_TYPES:
        logger.warning("event %s has unknown type %r", event_in.id, event_in.type)

    return Event(
        **event_in.model_dump(),
        ingested_at=(now or datetime.now(tz=timezone.utc)),
        normalized_entity=event_in.entity.strip().lower(),
    )
