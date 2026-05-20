"""Normalization tests."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.normalize import normalize


def _raw(**overrides):
    base = {
        "id": "evt-x",
        "source": "sensor-feed",
        "type": "movement",
        "timestamp": "2026-01-01T10:00:00Z",
        "entity": "Unit-Alpha",
        "location": "Region-A",
        "confidence": 0.5,
        "description": "test",
        "related_entities": [],
    }
    base.update(overrides)
    return base


def test_normalize_lowercases_entity():
    event = normalize(_raw(entity="  Unit-Alpha  "))
    assert event.entity == "  Unit-Alpha  "       # original preserved
    assert event.normalized_entity == "unit-alpha"  # query form


def test_normalize_rejects_naive_timestamp():
    with pytest.raises(ValidationError):
        normalize(_raw(timestamp="2026-01-01T10:00:00"))  # no offset


def test_normalize_rejects_out_of_range_confidence():
    with pytest.raises(ValidationError):
        normalize(_raw(confidence=1.5))


def test_normalize_defaults_related_entities():
    raw = _raw()
    raw.pop("related_entities")
    event = normalize(raw)
    assert event.related_entities == []


def test_normalize_strips_related_entities():
    event = normalize(_raw(related_entities=["  unit-bravo ", "", "unit-charlie"]))
    assert event.related_entities == ["unit-bravo", "unit-charlie"]


def test_normalize_accepts_unknown_type(caplog):
    # Unknown type passes through but logs a warning.
    with caplog.at_level("WARNING"):
        event = normalize(_raw(type="biometric"))
    assert event.type == "biometric"
    assert any("unknown type" in rec.message for rec in caplog.records)
