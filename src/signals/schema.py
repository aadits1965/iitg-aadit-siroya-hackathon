"""Versioned signal schema — the engine's downstream contract (Phase 2.5)."""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field

SIGNAL_SCHEMA_VERSION = "1.0.0"


class SentimentBlock(BaseModel):
    score: float
    label: str
    confidence: float
    model: str


class EventBlock(BaseModel):
    event_class: str
    confidence: float
    method: str


class ImpactBlock(BaseModel):
    score: float
    components: dict[str, float]


class Signal(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    signal_id: str
    schema_version: str = SIGNAL_SCHEMA_VERSION
    created_at_utc: datetime
    doc_ids: list[str]
    sources: list[str]
    tickers: list[str]
    sectors: list[str] = Field(default_factory=list)
    countries: list[str] = Field(default_factory=list)
    macro_tags: list[str] = Field(default_factory=list)
    sentiment: SentimentBlock
    event: EventBlock
    impact: ImpactBlock
    model_versions: dict[str, str] = Field(default_factory=dict)
    text_preview: str = ""


def make_signal_id(doc_ids: list[str]) -> str:
    basis = "|".join(sorted(doc_ids))
    digest = hashlib.sha256(basis.encode("utf-8")).hexdigest()
    return f"sig_{digest[:16]}"


def now_utc() -> datetime:
    return datetime.now(timezone.utc)
