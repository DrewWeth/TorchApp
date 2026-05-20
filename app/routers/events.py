"""/events endpoints."""

from __future__ import annotations

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from app.models import Event, EventIn
from app.normalize import normalize
from app.repository import EventExists, EventRepository

router = APIRouter(prefix="/events", tags=["events"])


def get_repo() -> EventRepository:
    # Overridden in main.py via dependency_overrides; tests inject their own.
    raise RuntimeError("repository dependency not configured")


@router.get("", response_model=list[Event])
async def list_events(
    repo: Annotated[EventRepository, Depends(get_repo)],
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> list[Event]:
    return await repo.list(limit=limit, offset=offset)


@router.get("/search", response_model=list[Event])
async def search_events(
    repo: Annotated[EventRepository, Depends(get_repo)],
    type: Optional[str] = None,
    entity: Optional[str] = None,
    location: Optional[str] = None,
    min_confidence: Annotated[Optional[float], Query(ge=0.0, le=1.0)] = None,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> list[Event]:
    # Route ordering matters: /search must be declared before /{event_id}, or
    # FastAPI will match "search" as an event id.
    return await repo.search(
        type=type,
        entity=entity,
        location=location,
        min_confidence=min_confidence,
        limit=limit,
        offset=offset,
    )


@router.get("/{event_id}", response_model=Event)
async def get_event(
    event_id: str,
    repo: Annotated[EventRepository, Depends(get_repo)],
) -> Event:
    event = await repo.get(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail=f"event {event_id!r} not found")
    return event


@router.post("", response_model=Event, status_code=status.HTTP_201_CREATED)
async def create_event(
    payload: EventIn,
    response: Response,
    repo: Annotated[EventRepository, Depends(get_repo)],
) -> Event:
    event = normalize(payload)
    try:
        stored = await repo.add(event)
    except EventExists:
        raise HTTPException(
            status_code=409, detail=f"event {event.id!r} already exists"
        )
    response.headers["Location"] = f"/events/{stored.id}"
    return stored
