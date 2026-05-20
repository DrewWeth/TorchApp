"""End-to-end API tests via fastapi.testclient."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_healthz(client: TestClient):
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_list_events_returns_seed(client: TestClient):
    r = client.get("/events")
    assert r.status_code == 200
    ids = {e["id"] for e in r.json()}
    assert ids == {"evt-101", "evt-102", "evt-103", "evt-104"}


def test_get_event_by_id(client: TestClient):
    r = client.get("/events/evt-101")
    assert r.status_code == 200
    assert r.json()["entity"] == "unit-alpha"


def test_get_event_missing_returns_404(client: TestClient):
    r = client.get("/events/does-not-exist")
    assert r.status_code == 404


def test_search_filters_combine(client: TestClient):
    r = client.get(
        "/events/search",
        params={"type": "movement", "min_confidence": 0.9},
    )
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["id"] == "evt-101"


def test_search_returns_empty_when_no_match(client: TestClient):
    r = client.get("/events/search", params={"type": "movement", "location": "Region-Z"})
    assert r.status_code == 200
    assert r.json() == []


def test_post_event_round_trip(client: TestClient):
    payload = {
        "id": "evt-999",
        "source": "sensor-feed",
        "type": "movement",
        "timestamp": "2026-01-01T11:00:00Z",
        "entity": "unit-delta",
        "location": "Region-C",
        "confidence": 0.5,
        "description": "fresh",
        "related_entities": [],
    }
    r = client.post("/events", json=payload)
    assert r.status_code == 201, r.text
    assert r.headers["Location"] == "/events/evt-999"

    r2 = client.get("/events/evt-999")
    assert r2.status_code == 200
    assert r2.json()["entity"] == "unit-delta"


def test_post_event_rejects_bad_confidence(client: TestClient):
    payload = {
        "id": "evt-bad",
        "source": "sensor-feed",
        "type": "movement",
        "timestamp": "2026-01-01T11:00:00Z",
        "entity": "unit-delta",
        "location": "Region-C",
        "confidence": 1.5,
        "description": "bad",
    }
    r = client.post("/events", json=payload)
    assert r.status_code == 422


def test_post_event_rejects_duplicate_id(client: TestClient):
    payload = {
        "id": "evt-101",  # already in seed
        "source": "sensor-feed",
        "type": "movement",
        "timestamp": "2026-01-01T11:00:00Z",
        "entity": "unit-delta",
        "location": "Region-C",
        "confidence": 0.5,
        "description": "dup",
    }
    r = client.post("/events", json=payload)
    assert r.status_code == 409


def test_entity_relationships(client: TestClient):
    r = client.get("/entities/unit-alpha/relationships")
    assert r.status_code == 200
    body = r.json()
    assert body["entity"] == "unit-alpha"
    assert {e["id"] for e in body["direct_events"]} == {"evt-101", "evt-104"}
    assert {e["id"] for e in body["mentioned_in"]} == {"evt-102"}
    assert "unit-bravo" in body["co_occurring_entities"]


def test_entity_relationships_unknown_404(client: TestClient):
    r = client.get("/entities/nobody/relationships")
    assert r.status_code == 404
