"""Pydantic models for the event service.

Three layers:
- EventIn: what clients POST. Strict validation, no server-assigned fields.
- Event:   what we store and return. Adds ingested_at + normalized_entity.
- RelationshipResponse: shape returned by /entities/{id}/relationships.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


KNOWN_EVENT_TYPES = ("movement", "observation", "signal", "alert", "note")
EventType = Literal["movement", "observation", "signal", "alert", "note"]


class EventIn(BaseModel):
    """Incoming event payload (POST /events).

    Unknown `type` values are accepted as plain strings so new sources can ship
    without a schema change — we log a warning at normalize-time instead of
    rejecting. Confidence is bounded; timestamps must be tz-aware (Pydantic v2
    accepts ISO 8601 with offset and rejects naive datetimes when we coerce).
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=128)
    source: str = Field(min_length=1, max_length=128)
    type: str = Field(min_length=1, max_length=64)
    timestamp: datetime
    entity: str = Field(min_length=1, max_length=128)
    location: str = Field(min_length=1, max_length=128)
    confidence: float = Field(ge=0.0, le=1.0)
    description: str = Field(max_length=4096)
    related_entities: list[str] = Field(default_factory=list)

    @field_validator("timestamp")
    @classmethod
    def require_tz(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware (include offset)")
        return v

    @field_validator("related_entities")
    @classmethod
    def strip_related(cls, v: list[str]) -> list[str]:
        return [s.strip() for s in v if s and s.strip()]


class Event(EventIn):
    """Stored/returned event. Extends EventIn with server-assigned fields."""

    ingested_at: datetime
    normalized_entity: str


class RelationshipResponse(BaseModel):
    """Structured relationships for one entity."""

    entity: str
    direct_events: list[Event]
    mentioned_in: list[Event]
    co_occurring_entities: list[str]
    temporal_neighbors: list[TemporalNeighbor]


class TemporalNeighbor(BaseModel):
    """An event near the queried entity's events in time (and optionally location)."""

    event_id: str
    delta_seconds: int
    same_location: bool


RelationshipResponse.model_rebuild()
