"""Phase 2 test: signal API filtering, against a temp SQLite DB (not the real
results/signals.db, so tests never depend on or mutate real engine output)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

import src.signals.store as store_module
from src.api.main import app
from src.signals.schema import EventBlock, ImpactBlock, Signal, SentimentBlock, make_signal_id
from src.signals.store import append_signal, get_conn

UTC = timezone.utc


def _signal(impact_score: float, event_class: str, created_at) -> Signal:
    return Signal(
        signal_id=make_signal_id([str(impact_score), event_class, created_at.isoformat()]),
        created_at_utc=created_at,
        doc_ids=["d1"],
        sources=["gdelt"],
        tickers=["AAPL"],
        sentiment=SentimentBlock(score=0.5, label="positive", confidence=0.9, model="test"),
        event=EventBlock(event_class=event_class, confidence=0.9, method="rule"),
        impact=ImpactBlock(score=impact_score, components={}),
    )


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "test_signals.db"
    jsonl_path = tmp_path / "test_signals.jsonl"
    monkeypatch.setattr(store_module, "SIGNALS_DB", db_path)
    monkeypatch.setattr(store_module, "SIGNALS_JSONL", jsonl_path)

    conn = get_conn(db_path)
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    append_signal(_signal(9.0, "Geopolitical", t0), conn=conn, jsonl_path=jsonl_path)
    append_signal(_signal(3.0, "Product Launch", t0 + timedelta(hours=1)), conn=conn, jsonl_path=jsonl_path)
    append_signal(_signal(8.0, "Credit Event", t0 + timedelta(hours=2)), conn=conn, jsonl_path=jsonl_path)
    conn.close()

    return TestClient(app)


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_min_impact_filter(client):
    r = client.get("/signals", params={"min_impact": 7})
    body = r.json()
    assert body["count"] == 2
    assert all(s["impact"]["score"] >= 7 for s in body["signals"])


def test_event_class_filter(client):
    r = client.get("/signals", params={"event_class": "Geopolitical"})
    body = r.json()
    assert body["count"] == 1
    assert body["signals"][0]["event"]["event_class"] == "Geopolitical"


def test_results_ordered_newest_first(client):
    r = client.get("/signals")
    created = [s["created_at_utc"] for s in r.json()["signals"]]
    assert created == sorted(created, reverse=True)
