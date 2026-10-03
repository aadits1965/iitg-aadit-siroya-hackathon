"""Phase 1 tests: schema validation, GDELT parsing (against a fixture shaped like
the real confirmed schema — see docs/DATA_VERIFICATION.md section 8), and dedup."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from src.ingestion.dedup import dedup_documents
from src.ingestion.news_gdelt import GdeltAdapter
from src.ingestion.schema import Document, SourceType, make_doc_id

UTC = timezone.utc


def _doc(title: str, dt: datetime, source="gdelt", source_type=SourceType.NEWS, doc_id=None) -> Document:
    return Document(
        doc_id=doc_id or make_doc_id(source, title),
        source=source,
        source_type=source_type,
        published_at_utc=dt,
        retrieved_at_utc=dt,
        url=f"https://example.com/{abs(hash(title))}",
        title=title,
        text=title,
    )


class TestSchema:
    def test_rejects_empty_text(self):
        with pytest.raises(Exception):
            Document(
                doc_id="x",
                source="gdelt",
                source_type=SourceType.NEWS,
                published_at_utc=datetime.now(UTC),
                retrieved_at_utc=datetime.now(UTC),
                text="   ",
            )

    def test_naive_datetime_coerced_to_utc(self):
        d = _doc("Fed raises rates", datetime(2026, 1, 1, 12, 0, 0))
        assert d.published_at_utc.tzinfo is not None

    def test_make_doc_id_deterministic(self):
        a = make_doc_id("gdelt", "https://x.com/1")
        b = make_doc_id("gdelt", "https://x.com/1")
        c = make_doc_id("gdelt", "https://x.com/2")
        assert a == b
        assert a != c


class TestGdeltParsing:
    """Fixture mirrors GDELT's real confirmed JSON schema (title/url/seendate/domain/
    language/sourcecountry/socialimage) — this is test fixture data, not live traffic."""

    FIXTURE = {
        "articles": [
            {
                "title": "Apple Reports Record Quarterly Revenue",
                "url": "https://example-news.com/apple-earnings",
                "url_mobile": "https://m.example-news.com/apple-earnings",
                "domain": "example-news.com",
                "seendate": "20260115T093000Z",
                "language": "English",
                "sourcecountry": "United States",
                "socialimage": "https://example-news.com/img.jpg",
            },
            {
                # malformed: missing title -> must be skipped, not crash
                "url": "https://example-news.com/broken",
                "seendate": "20260115T100000Z",
                "language": "English",
            },
        ]
    }

    def test_parses_valid_article_and_skips_malformed(self, monkeypatch):
        adapter = GdeltAdapter()
        monkeypatch.setattr(adapter, "_get", lambda params: self.FIXTURE)
        docs = list(adapter.fetch_live(queries=["Apple"], max_records=10))
        assert len(docs) == 1
        d = docs[0]
        assert d.title == "Apple Reports Record Quarterly Revenue"
        assert d.text == d.title  # headline-level only, confirmed design constraint
        assert d.source_type == SourceType.NEWS
        assert d.published_at_utc == datetime(2026, 1, 15, 9, 30, 0, tzinfo=UTC)

    def test_handles_no_data(self, monkeypatch):
        adapter = GdeltAdapter()
        monkeypatch.setattr(adapter, "_get", lambda params: None)
        docs = list(adapter.fetch_live(queries=["Nothing"], max_records=10))
        assert docs == []


class TestDedup:
    def test_exact_duplicate_title_dropped(self):
        t0 = datetime(2026, 1, 1, tzinfo=UTC)
        docs = [
            _doc("Fed raises interest rates by 25bps", t0, doc_id="a"),
            _doc("Fed raises interest rates by 25bps", t0 + timedelta(minutes=5), doc_id="b"),
        ]
        result = dedup_documents(docs)
        assert len(result.kept) == 1
        assert result.dropped_exact == 1

    def test_fuzzy_near_duplicate_dropped_within_window(self):
        t0 = datetime(2026, 1, 1, tzinfo=UTC)
        docs = [
            _doc("Fed raises interest rates by 25 basis points", t0, doc_id="a"),
            _doc("Fed raises interest rate by 25 basis point", t0 + timedelta(hours=1), doc_id="b"),
        ]
        result = dedup_documents(docs)
        assert len(result.kept) == 1
        assert result.dropped_fuzzy == 1

    def test_distinct_stories_both_kept(self):
        t0 = datetime(2026, 1, 1, tzinfo=UTC)
        docs = [
            _doc("Fed raises interest rates", t0, doc_id="a"),
            _doc("Apple announces new iPhone", t0 + timedelta(minutes=5), doc_id="b"),
        ]
        result = dedup_documents(docs)
        assert len(result.kept) == 2
        assert result.total_dropped == 0

    def test_near_duplicate_outside_window_both_kept(self):
        t0 = datetime(2026, 1, 1, tzinfo=UTC)
        docs = [
            _doc("Fed raises interest rates by 25 basis points", t0, doc_id="a"),
            _doc("Fed raises interest rate by 25 basis point", t0 + timedelta(hours=72), doc_id="b"),
        ]
        result = dedup_documents(docs)
        assert len(result.kept) == 2  # syndication window elapsed; treat as separate coverage
