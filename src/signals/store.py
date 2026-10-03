"""Signal persistence: append-only JSONL (source of truth, easy to diff/replay) plus
a SQLite table (so the API can filter/query without reparsing the file each time)."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from src.signals.schema import Signal

RESULTS_DIR = Path(__file__).resolve().parents[2] / "results"
SIGNALS_JSONL = RESULTS_DIR / "signals.jsonl"
SIGNALS_DB = RESULTS_DIR / "signals.db"

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS signals (
    signal_id TEXT PRIMARY KEY,
    created_at_utc TEXT NOT NULL,
    tickers TEXT NOT NULL,
    event_class TEXT NOT NULL,
    impact_score REAL NOT NULL,
    sentiment_score REAL NOT NULL,
    payload_json TEXT NOT NULL
);
"""


def get_conn(db_path: Path | None = None) -> sqlite3.Connection:
    # Resolved at call time (not as a default-argument value) so that tests can
    # monkeypatch the module-level SIGNALS_DB and have it actually take effect.
    if db_path is None:
        db_path = SIGNALS_DB
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute(_CREATE_TABLE)
    conn.commit()
    return conn


def append_signal(signal: Signal, conn: sqlite3.Connection | None = None, jsonl_path: Path | None = None) -> None:
    if jsonl_path is None:
        jsonl_path = SIGNALS_JSONL
    owns_conn = conn is None
    if conn is None:
        conn = get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO signals (signal_id, created_at_utc, tickers, event_class, "
        "impact_score, sentiment_score, payload_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            signal.signal_id,
            signal.created_at_utc.isoformat(),
            json.dumps(signal.tickers),
            signal.event.event_class,
            signal.impact.score,
            signal.sentiment.score,
            signal.model_dump_json(),
        ),
    )
    conn.commit()
    if owns_conn:
        conn.close()

    jsonl_path.parent.mkdir(parents=True, exist_ok=True)
    with jsonl_path.open("a", encoding="utf-8") as f:
        f.write(signal.model_dump_json() + "\n")


def query_signals(
    conn: sqlite3.Connection,
    since_utc: str | None = None,
    min_impact: float | None = None,
    event_class: str | None = None,
    limit: int = 200,
) -> list[dict]:
    clauses = []
    params: list = []
    if since_utc:
        clauses.append("created_at_utc >= ?")
        params.append(since_utc)
    if min_impact is not None:
        clauses.append("impact_score >= ?")
        params.append(min_impact)
    if event_class:
        clauses.append("event_class = ?")
        params.append(event_class)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = conn.execute(
        f"SELECT payload_json FROM signals {where} ORDER BY created_at_utc DESC LIMIT ?",
        (*params, limit),
    ).fetchall()
    return [json.loads(r[0]) for r in rows]
