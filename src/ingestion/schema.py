"""Common normalised record schema every source adapter must produce."""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


class SourceType(str, Enum):
    NEWS = "news"
    SOCIAL = "social"


def make_doc_id(source: str, url_or_uid: str) -> str:
    """Deterministic id so re-ingesting the same item is idempotent."""
    digest = hashlib.sha256(f"{source}|{url_or_uid}".encode("utf-8")).hexdigest()
    return f"{source}_{digest[:16]}"


class Document(BaseModel):
    doc_id: str
    source: str  # e.g. "gdelt", "mastodon", "twitter_replay"
    source_type: SourceType
    published_at_utc: datetime
    retrieved_at_utc: datetime
    url: Optional[str] = None
    title: Optional[str] = None
    text: str
    lang: str = "en"
    raw_meta: dict[str, Any] = Field(default_factory=dict)

    @field_validator("published_at_utc", "retrieved_at_utc")
    @classmethod
    def _ensure_utc(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        return v.astimezone(timezone.utc)

    @field_validator("text")
    @classmethod
    def _non_empty_text(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("text must not be empty")
        return v.strip()

    def normalized_title_hash(self) -> str:
        """Used by dedup: lowercase, strip punctuation-ish whitespace collapse."""
        basis = (self.title or self.text)[:200].lower()
        basis = "".join(ch for ch in basis if ch.isalnum() or ch.isspace())
        basis = " ".join(basis.split())
        return hashlib.sha1(basis.encode("utf-8")).hexdigest()
