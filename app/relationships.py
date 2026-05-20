"""Relationship logic over a set of events.

Three notions of "related" from the spec:
  1. Same entity            → direct_events
  2. Shared related_entities → mentioned_in + co_occurring_entities
  3. Same location, close in time → temporal_neighbors

Functions are pure: they take the candidate events and a target entity,
return derived structures. The router does the I/O.
"""

from __future__ import annotations

from app.models import Event, RelationshipResponse, TemporalNeighbor


def build_relationships(
    entity_id: str,
    events_for_entity: list[Event],
    all_events: list[Event],
    *,
    window_seconds: int,
) -> RelationshipResponse:
    """Assemble the response for /entities/{entity_id}/relationships.

    - events_for_entity: events where entity_id appears as primary or related.
    - all_events: full corpus, used to find temporal neighbours.
    - window_seconds: max |Δt| (in seconds) to count as a temporal neighbour.
    """
    target = entity_id.strip().lower()

    direct: list[Event] = []
    mentioned: list[Event] = []
    co_occurring: set[str] = set()

    for e in events_for_entity:
        related_norm = {r.strip().lower() for r in e.related_entities}
        if e.normalized_entity == target:
            direct.append(e)
        if target in related_norm:
            mentioned.append(e)
        # Anyone else who appears on an event involving the target.
        co_occurring.update(related_norm)
        co_occurring.add(e.normalized_entity)
    co_occurring.discard(target)

    neighbours = _temporal_neighbours(events_for_entity, all_events, window_seconds)

    return RelationshipResponse(
        entity=target,
        direct_events=sorted(direct, key=lambda e: e.timestamp),
        mentioned_in=sorted(mentioned, key=lambda e: e.timestamp),
        co_occurring_entities=sorted(co_occurring),
        temporal_neighbors=neighbours,
    )


def _temporal_neighbours(
    events_for_entity: list[Event],
    all_events: list[Event],
    window_seconds: int,
) -> list[TemporalNeighbor]:
    """Find events within `window_seconds` of any event-for-entity.

    Excludes the events_for_entity themselves to avoid self-matches. For each
    neighbour we record the smallest |Δt| against the entity's events and
    whether at least one of those near-in-time pairings shares a location.
    """
    if not events_for_entity:
        return []

    own_ids = {e.id for e in events_for_entity}
    neighbours: dict[str, TemporalNeighbor] = {}

    for other in all_events:
        if other.id in own_ids:
            continue
        best: TemporalNeighbor | None = None
        for owned in events_for_entity:
            delta = int(abs((other.timestamp - owned.timestamp).total_seconds()))
            if delta > window_seconds:
                continue
            same_loc = other.location.strip().lower() == owned.location.strip().lower()
            if best is None or delta < best.delta_seconds:
                best = TemporalNeighbor(
                    event_id=other.id, delta_seconds=delta, same_location=same_loc
                )
        if best is not None:
            neighbours[other.id] = best

    return sorted(neighbours.values(), key=lambda n: n.delta_seconds)
