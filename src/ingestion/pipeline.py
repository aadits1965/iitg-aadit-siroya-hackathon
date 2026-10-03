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


def build_all_caches(gdelt_max_records: int = 25, mastodon_limit_per_tag: int = 20, replay_limit: int = 300) -> list[IngestStats]:
    """Pulls every source once and writes each to its own cache file in data/cache/.
    Designed to be re-run (idempotent file overwrite) from a clean network connection."""
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

    return all_stats
