"""Orchestrates adapters -> dedup -> cache write. Used by scripts/build_cache.py
and by the --live polling loop in run.py (Phase 5)."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import yaml

from src.ingestion.dedup import dedup_documents
from src.ingestion.news_gdelt import GdeltAdapter
from src.ingestion.schema import Document
from src.ingestion.social_mastodon import MastodonAdapter
from src.ingestion.social_twitter_replay import TwitterReplayAdapter

logger = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "queries.yaml"
CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "cache"
RAW_SAMPLES_DIR = Path(__file__).resolve().parents[2] / "data" / "raw_samples"


def load_queries() -> dict:
    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


@dataclass
class IngestStats:
    source: str
    fetched: int
    kept_after_dedup: int
    dropped_exact: int
    dropped_fuzzy: int


def ingest_gdelt(max_records: int = 25, timespan: str = "7d") -> tuple[list[Document], IngestStats]:
    cfg = load_queries()
    queries = cfg["companies"] + cfg["macro_geopolitical"]
    adapter = GdeltAdapter()
    docs = list(adapter.fetch_live(queries=queries, max_records=max_records, timespan=timespan))
    result = dedup_documents(docs)
    stats = IngestStats("gdelt", len(docs), len(result.kept), result.dropped_exact, result.dropped_fuzzy)
    return result.kept, stats


EVENT_STUDY_UNIVERSE_PATH = Path(__file__).resolve().parents[2] / "data" / "universe_event_study.csv"


def ingest_gdelt_event_study(max_records: int = 25, timespan: str = "18m") -> tuple[list[Document], IngestStats]:
    """Wider pull (80 companies, see data/universe_event_study.csv) used only to
    get the Phase 3 event study's sample size up -- separate from the core
    20-ticker ingest_gdelt() used by the dashboard/Module B. Longer timespan
    (GDELT's own docs indicate per-query lookback up to ~1.5 years is usable,
    see docs/DATA_VERIFICATION.md section 8) to maximise the number of resolvable
    headlines. This alone is ~80 queries x GDELT's 5s self-throttle -- budget
    ~10-15 minutes even on a clean connection."""
    import csv as _csv

    with EVENT_STUDY_UNIVERSE_PATH.open("r", encoding="utf-8") as f:
        queries = [row["company_name"] for row in _csv.DictReader(f)]
    adapter = GdeltAdapter()
    docs = list(adapter.fetch_live(queries=queries, max_records=max_records, timespan=timespan))
    result = dedup_documents(docs)
    stats = IngestStats("gdelt_event_study", len(docs), len(result.kept), result.dropped_exact, result.dropped_fuzzy)
    return result.kept, stats


def ingest_mastodon(limit_per_tag: int = 20) -> tuple[list[Document], IngestStats]:
    cfg = load_queries()
    hashtags = cfg["social_hashtags"]
    adapter = MastodonAdapter()
    docs = list(adapter.fetch_live(hashtags=hashtags, limit_per_tag=limit_per_tag))
    result = dedup_documents(docs)
    stats = IngestStats("mastodon", len(docs), len(result.kept), result.dropped_exact, result.dropped_fuzzy)
    return result.kept, stats


def ingest_twitter_replay(limit: int = 300) -> tuple[list[Document], IngestStats]:
    adapter = TwitterReplayAdapter()
    docs = list(adapter.fetch_live(split="train", limit=limit))
    # No dedup needed: dataset rows are already distinct curated tweets, and the
    # synthetic shared timestamp would make the fuzzy-window logic meaningless.
    stats = IngestStats("twitter_replay", len(docs), len(docs), 0, 0)
    return docs, stats


def build_all_caches(
    gdelt_max_records: int = 25,
    mastodon_limit_per_tag: int = 20,
    replay_limit: int = 300,
    include_event_study_gdelt: bool = True,
    include_market_data: bool = True,
) -> list[IngestStats]:
    """Pulls every source once and writes each to its own cache file in data/cache/.
    Designed to be re-run (idempotent file overwrite) from a clean network connection.
    include_event_study_gdelt adds ~80 extra GDELT queries (~10-15 min) to build
    the wider sample the Phase 3 event study needs for statistical power --
    see docs/EVALUATION.md section 3."""
    from src.ingestion.base import SourceAdapter

    all_stats = []

    try:
        gdelt_docs, gdelt_stats = ingest_gdelt()
        SourceAdapter.write_jsonl(gdelt_docs, CACHE_DIR / "news_gdelt.jsonl")
        all_stats.append(gdelt_stats)
        logger.info("gdelt: %s", gdelt_stats)
    except Exception:
        logger.exception("gdelt ingestion failed; cache left untouched")

    try:
        mastodon_docs, mastodon_stats = ingest_mastodon()
        SourceAdapter.write_jsonl(mastodon_docs, CACHE_DIR / "social_mastodon.jsonl")
        all_stats.append(mastodon_stats)
        logger.info("mastodon: %s", mastodon_stats)
    except Exception:
        logger.exception("mastodon ingestion failed; cache left untouched")

    try:
        replay_docs, replay_stats = ingest_twitter_replay(limit=replay_limit)
        SourceAdapter.write_jsonl(replay_docs, RAW_SAMPLES_DIR / "social_twitter_replay.jsonl")
        all_stats.append(replay_stats)
        logger.info("twitter_replay: %s", replay_stats)
    except Exception:
        logger.exception("twitter_replay ingestion failed; cache left untouched")

    if include_event_study_gdelt:
        try:
            es_docs, es_stats = ingest_gdelt_event_study(max_records=gdelt_max_records)
            SourceAdapter.write_jsonl(es_docs, CACHE_DIR / "news_gdelt_event_study.jsonl")
            all_stats.append(es_stats)
            logger.info("gdelt_event_study: %s", es_stats)
        except Exception:
            logger.exception("gdelt event-study ingestion failed; cache left untouched")

    if include_market_data:
        try:
            from datetime import date, timedelta

            from src.ingestion.market_data import fetch_equity_prices, fetch_fred_series, fetch_treasury_curve

            fetch_treasury_curve()

            import csv as _csv

            with EVENT_STUDY_UNIVERSE_PATH.open("r", encoding="utf-8") as f:
                es_tickers = [row["ticker"] for row in _csv.DictReader(f)]
            with (Path(__file__).resolve().parents[2] / "data" / "universe.csv").open("r", encoding="utf-8") as f:
                core_tickers = [row["ticker"] for row in _csv.DictReader(f)]
            all_tickers = sorted(set(es_tickers) | set(core_tickers))
            fetch_equity_prices(all_tickers, start=date.today() - timedelta(days=550), end=date.today())

            import os

            fred_key = os.environ.get("FRED_API_KEY")
            if fred_key:
                fetch_fred_series(["BAMLH0A0HYM2", "BAMLC0A0CM"], api_key=fred_key)
            else:
                logger.warning("FRED_API_KEY not set in .env -- skipping credit-spread series fetch "
                                "(optional; Module B's shock library can still use documented illustrative "
                                "spread assumptions without it)")
        except Exception:
            logger.exception("market data fetch failed; cache left untouched")

    return all_stats
