"""Offline replay adapter: zeroshot/twitter-financial-news-sentiment (MIT licensed).

Confirmed via the HF datasets-server /info endpoint (2026-10-04): schema is only
`text` (string) and `label` (int64) — there is NO timestamp field in this dataset.
It is therefore used only as a deterministic --demo replay stream, and is excluded
from the Phase 3 event study (which needs real dates and uses GDELT instead).

Because there is no genuine post time, `published_at_utc` is set to the time this
adapter pulled/replayed the row (never a fabricated historical date), and
`raw_meta["timestamp_is_synthetic"] = True` makes that explicit everywhere
downstream. Label mapping (0=Bearish,1=Bullish,2=Neutral -> negative/positive/neutral)
is documented as an assumption in docs/ASSUMPTIONS.md.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Iterator

import requests

from src.ingestion.base import SourceAdapter
from src.ingestion.schema import Document, SourceType, make_doc_id

logger = logging.getLogger(__name__)

DATASETS_SERVER_URL = "https://datasets-server.huggingface.co/rows"
DATASET_ID = "zeroshot/twitter-financial-news-sentiment"
LABEL_MAP = {0: "negative", 1: "positive", 2: "neutral"}  # Bearish/Bullish/Neutral -> polarity


class TwitterReplayAdapter(SourceAdapter):
    name = "twitter_replay"

    def __init__(self, timeout_s: float = 20.0):
        self.timeout_s = timeout_s

    def fetch_live(self, split: str = "train", limit: int = 300, offset: int = 0) -> Iterator[Document]:
        """Despite the method name (shared interface with other adapters), this pulls a
        static, licensed dataset rather than a real-time feed — see module docstring."""
        now = datetime.now(timezone.utc)
        page_size = 100
        fetched = 0
        cursor = offset
        while fetched < limit:
            length = min(page_size, limit - fetched)
            params = {
                "dataset": DATASET_ID,
                "config": "default",
                "split": split,
                "offset": cursor,
                "length": length,
            }
            try:
                resp = requests.get(DATASETS_SERVER_URL, params=params, timeout=self.timeout_s)
            except requests.RequestException as e:
                logger.warning("twitter_replay fetch failed: %s", e)
                break
            if resp.status_code != 200:
                logger.warning("twitter_replay non-200: %s", resp.status_code)
                break
            payload = resp.json()
            rows = payload.get("rows", [])
            if not rows:
                break
            for r in rows:
                row = r.get("row", {})
                text = row.get("text")
                label = row.get("label")
                if not text or label is None:
                    continue
                row_idx = r.get("row_idx")
                yield Document(
                    doc_id=make_doc_id(self.name, f"{split}_{row_idx}"),
                    source=self.name,
                    source_type=SourceType.SOCIAL,
                    published_at_utc=now,
                    retrieved_at_utc=now,
                    url=None,
                    title=None,
                    text=text,
                    lang="en",
                    raw_meta={
                        "dataset": DATASET_ID,
                        "split": split,
                        "row_idx": row_idx,
                        "gold_label_raw": label,
                        "gold_label_polarity": LABEL_MAP.get(label),
                        "timestamp_is_synthetic": True,
                        "license": "MIT",
                    },
                )
                fetched += 1
                if fetched >= limit:
                    break
            cursor += length
            if payload.get("num_rows_total") is not None and cursor >= payload["num_rows_total"]:
                break
