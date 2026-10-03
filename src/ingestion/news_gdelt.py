"""GDELT DOC 2.0 adapter. Headline-level only (the API has no article-body field —
confirmed live, see docs/DATA_VERIFICATION.md section 8). CC0-licensed, so cached
samples may be redistributed with attribution.

Confirmed response fields (live, 2026-10-04): url, url_mobile, title, seendate
(format YYYYMMDDTHHMMSSZ), domain, language, sourcecountry, socialimage.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Iterator, Optional

import requests

from src.ingestion.base import SourceAdapter
from src.ingestion.schema import Document, SourceType, make_doc_id

logger = logging.getLogger(__name__)

BASE_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
MIN_REQUEST_INTERVAL_S = 5.0  # GDELT's own stated minimum ("one every 5 seconds")
ATTRIBUTION = "Data via the GDELT Project (gdeltproject.org), CC0."


class GdeltAdapter(SourceAdapter):
    name = "gdelt"

    def __init__(self, timeout_s: float = 20.0, max_retries: int = 3):
        self.timeout_s = timeout_s
        self.max_retries = max_retries
        self._last_request_ts: float = 0.0

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request_ts
        if elapsed < MIN_REQUEST_INTERVAL_S:
            time.sleep(MIN_REQUEST_INTERVAL_S - elapsed)

    def _get(self, params: dict) -> Optional[dict]:
        backoff = 5.0
        for attempt in range(1, self.max_retries + 1):
            self._throttle()
            self._last_request_ts = time.monotonic()
            try:
                resp = requests.get(BASE_URL, params=params, timeout=self.timeout_s)
            except requests.RequestException as e:
                logger.warning("gdelt request failed (attempt %d): %s", attempt, e)
                time.sleep(backoff)
                backoff *= 2
                continue
            if resp.status_code == 429:
                logger.warning(
                    "gdelt 429 rate-limited (attempt %d/%d); backing off %.0fs",
                    attempt, self.max_retries, backoff,
                )
                time.sleep(backoff)
                backoff *= 2
                continue
            if resp.status_code != 200:
                logger.warning("gdelt non-200 status %s: %s", resp.status_code, resp.text[:200])
                return None
            try:
                return resp.json()
            except ValueError:
                logger.warning("gdelt returned non-JSON body (likely a throttle notice): %s", resp.text[:200])
                return None
        logger.error("gdelt: exhausted retries, giving up on query=%s", params.get("query"))
        return None

    @staticmethod
    def _parse_seendate(seendate: str) -> datetime:
        # Format confirmed live: "20260708T124500Z"
        return datetime.strptime(seendate, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)

    def fetch_live(
        self,
        queries: list[str],
        max_records: int = 50,
        timespan: str = "7d",
        english_only: bool = True,
    ) -> Iterator[Document]:
        now = datetime.now(timezone.utc)
        for q in queries:
            full_query = f"{q} sourcelang:english" if english_only else q
            params = {
                "query": full_query,
                "mode": "artlist",
                "format": "json",
                "maxrecords": max_records,
                "timespan": timespan,
                "sort": "DateDesc",
            }
            data = self._get(params)
            if not data:
                continue
            for art in data.get("articles", []):
                title = art.get("title")
                url = art.get("url")
                seendate = art.get("seendate")
                if not title or not url or not seendate:
                    continue
                try:
                    published = self._parse_seendate(seendate)
                except ValueError:
                    continue
                lang = (art.get("language") or "English")
                if english_only and lang.lower() not in ("english", "en"):
                    continue
                yield Document(
                    doc_id=make_doc_id(self.name, url),
                    source=self.name,
                    source_type=SourceType.NEWS,
                    published_at_utc=published,
                    retrieved_at_utc=now,
                    url=url,
                    title=title,
                    text=title,  # headline-level only; no body field in this API
                    lang="en",
                    raw_meta={
                        "domain": art.get("domain"),
                        "sourcecountry": art.get("sourcecountry"),
                        "query": q,
                        "attribution": ATTRIBUTION,
                    },
                )
