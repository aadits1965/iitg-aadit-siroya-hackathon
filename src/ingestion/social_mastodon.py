"""Mastodon public hashtag timeline adapter — live social source.

Confirmed working with no auth, 2026-10-04: GET https://mastodon.social/api/v1/timelines/tag/<hashtag>
returns 200 with real posts carrying a `created_at` timestamp. Published rate limit observed in
response headers: 300 requests / 5-minute window (x-ratelimit-limit / x-ratelimit-remaining /
x-ratelimit-reset). See docs/DATA_VERIFICATION.md section 8.
"""
from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timezone
from typing import Iterator

import requests

from src.ingestion.base import SourceAdapter
from src.ingestion.schema import Document, SourceType, make_doc_id

logger = logging.getLogger(__name__)

_TAG_RE = re.compile(r"<[^>]+>")  # Mastodon post `content` is HTML; strip tags for plain text


def _strip_html(html: str) -> str:
    text = _TAG_RE.sub(" ", html or "")
    return " ".join(text.split())


class MastodonAdapter(SourceAdapter):
    name = "mastodon"

    def __init__(self, instance: str = "mastodon.social", timeout_s: float = 15.0, min_interval_s: float = 1.0):
        self.instance = instance
        self.timeout_s = timeout_s
        self.min_interval_s = min_interval_s
        self._last_request_ts = 0.0

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request_ts
        if elapsed < self.min_interval_s:
            time.sleep(self.min_interval_s - elapsed)

    def fetch_live(self, hashtags: list[str], limit_per_tag: int = 20) -> Iterator[Document]:
        now = datetime.now(timezone.utc)
        for tag in hashtags:
            self._throttle()
            self._last_request_ts = time.monotonic()
            url = f"https://{self.instance}/api/v1/timelines/tag/{tag}"
            try:
                resp = requests.get(url, params={"limit": limit_per_tag}, timeout=self.timeout_s)
            except requests.RequestException as e:
                logger.warning("mastodon request failed for #%s: %s", tag, e)
                continue
            if resp.status_code != 200:
                logger.warning("mastodon non-200 for #%s: %s", tag, resp.status_code)
                continue
            for post in resp.json():
                text = _strip_html(post.get("content", ""))
                if not text:
                    continue
                lang = post.get("language") or "en"
                if lang != "en":
                    continue
                created_at = post.get("created_at")
                if not created_at:
                    continue
                published = datetime.fromisoformat(created_at.replace("Z", "+00:00")).astimezone(timezone.utc)
                post_url = post.get("url") or post.get("uri") or post.get("id")
                yield Document(
                    doc_id=make_doc_id(self.name, str(post.get("id") or post_url)),
                    source=self.name,
                    source_type=SourceType.SOCIAL,
                    published_at_utc=published,
                    retrieved_at_utc=now,
                    url=post_url,
                    title=None,
                    text=text,
                    lang="en",
                    raw_meta={
                        "hashtag": tag,
                        "instance": self.instance,
                        "favourites_count": post.get("favourites_count"),
                        "reblogs_count": post.get("reblogs_count"),
                    },
                )
