"""FastAPI signal API. Downstream modules "subscribe" by polling this endpoint
(or tailing results/signals.jsonl directly) — documented honestly as polling-based
pub/sub, not a real message bus (see docs/ASSUMPTIONS.md / deck Limitations slide)."""
from __future__ import annotations

from typing import Optional

from fastapi import FastAPI, Query

from src.signals.store import get_conn, query_signals

app = FastAPI(title="AI/NLP Risk Engine Signal API", version="1.0.0")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/signals")
def get_signals(
    since: Optional[str] = Query(None, description="ISO8601 UTC timestamp lower bound"),
    min_impact: Optional[float] = Query(None, ge=1.0, le=10.0),
    event_class: Optional[str] = Query(None),
    limit: int = Query(200, le=1000),
):
    conn = get_conn()
    try:
        rows = query_signals(conn, since_utc=since, min_impact=min_impact, event_class=event_class, limit=limit)
    finally:
        conn.close()
    return {"count": len(rows), "signals": rows}
