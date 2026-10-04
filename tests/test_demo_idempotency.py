"""Demo mode must be deterministic: running it twice from a clean state
produces byte-identical results/signals.jsonl and the same trigger decisions.

Two tests:
  - a fast one (always runs) that checks the determinism mechanism directly
    (RiskEngine.build_signals with a fake, deterministic scorer) -- this is
    what actually matters for correctness and runs in well under a second.
  - a real end-to-end one (opt-in, ~2 minutes: runs the real engine with
    real FinBERT twice via scripts/run_engine.py) that proves the full
    pipeline, including the real model, is genuinely reproducible. Skipped
    by default so the normal `pytest tests/ -q` run stays fast; run with
    `RUN_SLOW_TESTS=1 pytest tests/test_demo_idempotency.py -v`.
"""
from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from src.ingestion.schema import Document, SourceType, make_doc_id
from src.modules.stress_test.trigger import evaluate_signals
from src.nlp.engine import RiskEngine
from src.nlp.sentiment import SentimentResult

ROOT = Path(__file__).resolve().parents[1]
UTC = timezone.utc


class FakeSentimentScorer:
    def score(self, text: str) -> SentimentResult:
        # Deterministic function of the text itself, not of call order/time.
        score = (hash(text) % 2000 - 1000) / 1000.0
        label = "positive" if score > 0.05 else "negative" if score < -0.05 else "neutral"
        return SentimentResult(score=score, label=label, confidence=0.8, model="fake-deterministic")


def _doc(text, dt, source="gdelt", doc_id=None):
    return Document(
        doc_id=doc_id or make_doc_id(source, text),
        source=source,
        source_type=SourceType.NEWS,
        published_at_utc=dt,
        retrieved_at_utc=dt,
        url=f"https://example.com/{abs(hash(text))}",
        title=text,
        text=text,
    )


class TestBuildSignalsDeterminism:
    """Fast: validates the mechanism (fixed created_at_utc derived from doc
    timestamps, not wall-clock now()) directly."""

    def test_two_calls_on_same_docs_produce_identical_signals(self):
        t0 = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
        docs = [
            _doc("Tesla stock plunges after recall announcement", t0, doc_id="a"),
            _doc("Apple shares soar on record iPhone sales", t0 + timedelta(minutes=5), doc_id="b"),
            _doc("Fed raises interest rates amid inflation concerns", t0 + timedelta(minutes=10), doc_id="c"),
        ]

        engine1 = RiskEngine(sentiment_scorer=FakeSentimentScorer())
        signals1 = engine1.build_signals(docs)

        engine2 = RiskEngine(sentiment_scorer=FakeSentimentScorer())  # fresh engine, fresh cooldown state
        signals2 = engine2.build_signals(docs)

        assert len(signals1) == len(signals2)
        dump1 = [s.model_dump_json() for s in sorted(signals1, key=lambda s: s.signal_id)]
        dump2 = [s.model_dump_json() for s in sorted(signals2, key=lambda s: s.signal_id)]
        assert dump1 == dump2

    def test_created_at_utc_derived_from_doc_not_wall_clock(self):
        t0 = datetime(2020, 3, 15, 8, 30, tzinfo=UTC)  # deliberately not "now"
        docs = [_doc("Boeing grounded after safety incident", t0, doc_id="a")]
        engine = RiskEngine(sentiment_scorer=FakeSentimentScorer())
        signals = engine.build_signals(docs)
        assert signals[0].created_at_utc == t0


@pytest.mark.skipif(not os.environ.get("RUN_SLOW_TESTS"), reason="real end-to-end run (~2 min); set RUN_SLOW_TESTS=1")
class TestRealEngineIdempotency:
    def test_running_demo_engine_twice_is_byte_identical(self):
        signals_path = ROOT / "results" / "signals.jsonl"
        env = {**os.environ, "PYTHONIOENCODING": "utf-8"}

        subprocess.run([sys.executable, "scripts/run_engine.py"], cwd=ROOT, check=True, env=env)
        content1 = signals_path.read_bytes()

        subprocess.run([sys.executable, "scripts/run_engine.py"], cwd=ROOT, check=True, env=env)
        content2 = signals_path.read_bytes()

        assert content1 == content2, "results/signals.jsonl differs between two clean runs of the same cache"

        import json
        signals = [json.loads(line) for line in content2.decode("utf-8").splitlines() if line.strip()]
        decisions1 = evaluate_signals(signals)
        decisions2 = evaluate_signals(signals)
        fired1 = {d.signal_id for d in decisions1 if d.fired}
        fired2 = {d.signal_id for d in decisions2 if d.fired}
        assert fired1 == fired2
