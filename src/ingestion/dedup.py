"""De-duplication across and within sources: exact normalised-title hash first
(cheap), then fuzzy match on remaining pairs (rapidfuzz) within a time window."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from rapidfuzz import fuzz

from src.ingestion.schema import Document

FUZZY_THRESHOLD = 88.0  # token_sort_ratio 0-100
FUZZY_WINDOW = timedelta(hours=48)


@dataclass
class DedupResult:
    kept: list[Document]
    dropped_exact: int
    dropped_fuzzy: int

    @property
    def total_dropped(self) -> int:
        return self.dropped_exact + self.dropped_fuzzy


def dedup_documents(docs: list[Document]) -> DedupResult:
    """Docs are assumed already roughly time-sorted is NOT required; we sort internally."""
    ordered = sorted(docs, key=lambda d: d.published_at_utc)

    seen_hashes: dict[str, Document] = {}
    exact_dropped = 0
    stage1: list[Document] = []
    for d in ordered:
        h = d.normalized_title_hash()
        if h in seen_hashes:
            exact_dropped += 1
            continue
        seen_hashes[h] = d
        stage1.append(d)

    kept: list[Document] = []
    fuzzy_dropped = 0
    for d in stage1:
        basis = (d.title or d.text)[:200]
        is_dup = False
        for k in reversed(kept):
            if (d.published_at_utc - k.published_at_utc) > FUZZY_WINDOW:
                break  # kept is time-ordered; nothing older is within window either
            k_basis = (k.title or k.text)[:200]
            score = fuzz.token_sort_ratio(basis, k_basis)
            if score >= FUZZY_THRESHOLD:
                is_dup = True
                break
        if is_dup:
            fuzzy_dropped += 1
        else:
            kept.append(d)

    return DedupResult(kept=kept, dropped_exact=exact_dropped, dropped_fuzzy=fuzzy_dropped)
