"""/entities endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from app.models import RelationshipResponse
from app.relationships import build_relationships
from app.repository import EventRepository
from app.routers.events import get_repo

router = APIRouter(prefix="/entities", tags=["entities"])


@router.get("/{entity_id}/relationships", response_model=RelationshipResponse)
async def get_entity_relationships(
    entity_id: str,
    repo: Annotated[EventRepository, Depends(get_repo)],
    window_minutes: int = Query(
        30,
        ge=0,
        le=24 * 60,
        description="Max minutes between event timestamps to count as a temporal neighbour.",
    ),
) -> RelationshipResponse:
    known = await repo.all_entities()
    if entity_id.strip().lower() not in known:
        raise HTTPException(
            status_code=404, detail=f"entity {entity_id!r} not found"
        )

    events_for_entity = await repo.events_for_entity(entity_id)
    all_events = await repo.list(limit=10_000, offset=0)
    return build_relationships(
        entity_id,
        events_for_entity,
        all_events,
        window_seconds=window_minutes * 60,
    )
