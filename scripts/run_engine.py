#!/usr/bin/env python
"""Run the NLP Risk Engine over cached ingested documents and write signals to
results/signals.jsonl + results/signals.db. This is the --demo path: fully
offline, deterministic, reads only from data/cache/ and data/raw_samples/.
"""
import argparse
import logging
import sys
import time
from pathlib import Path

# Real headline/tweet text can contain emoji etc.; Windows' default console
# codepage (cp1252) can't encode it and would otherwise crash this script's
# own prints with UnicodeEncodeError on a plain `python scripts/run_engine.py`
# run (run.py also sets PYTHONIOENCODING for its subprocess calls, but this
# script should be safe to run standalone too).
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.ingestion.base import SourceAdapter  # noqa: E402
from src.nlp.engine import RiskEngine  # noqa: E402
from src.nlp.sentiment import FinBertSentimentScorer, VaderSentimentScorer  # noqa: E402
from src.signals.store import SIGNALS_DB, SIGNALS_JSONL, append_signal, get_conn  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = ROOT / "data" / "cache"
RAW_SAMPLES_DIR = ROOT / "data" / "raw_samples"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


def load_cached_docs() -> list:
    docs = []
    for path in [
        CACHE_DIR / "news_gdelt.jsonl",
        CACHE_DIR / "social_mastodon.jsonl",
        RAW_SAMPLES_DIR / "social_twitter_replay.jsonl",
    ]:
        if path.exists():
            batch = list(SourceAdapter._read_jsonl(path))
            logger.info("loaded %d docs from %s", len(batch), path)
            docs.extend(batch)
        else:
            logger.warning("cache file missing, skipping: %s", path)
    return docs


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sentiment-model", choices=["finbert", "vader"], default="finbert")
    parser.add_argument("--limit", type=int, default=None, help="cap number of docs processed (for quick smoke tests)")
    args = parser.parse_args()

    docs = load_cached_docs()
    if args.limit:
        docs = docs[: args.limit]
    if not docs:
        logger.error("no cached documents found; run scripts/build_cache.py first")
        sys.exit(1)

    scorer = FinBertSentimentScorer() if args.sentiment_model == "finbert" else VaderSentimentScorer()
    engine = RiskEngine(sentiment_scorer=scorer)

    t0 = time.perf_counter()
    signals = engine.build_signals(docs)
    elapsed = time.perf_counter() - t0
    logger.info("built %d signals from %d docs in %.2fs (%.3fs/doc)", len(signals), len(docs), elapsed, elapsed / max(len(docs), 1))

    # This is a full deterministic rebuild from the cache, not an incremental
    # append -- clear any previous run's output first. append_signal() writes
    # JSONL in append mode (by design, for a genuine live/streaming run), so
    # without this, re-running this script (e.g. every `python run.py --mode
    # demo`) would silently accumulate duplicate signals across runs.
    for stale_path in (SIGNALS_JSONL, SIGNALS_DB):
        if stale_path.exists():
            stale_path.unlink()

    conn = get_conn()
    for sig in signals:
        append_signal(sig, conn=conn)
    conn.close()

    print("\n=== Engine run summary ===")
    print(f"docs processed:   {len(docs)}")
    print(f"signals produced: {len(signals)}")
    print(f"latency:          {elapsed:.2f}s total, {elapsed/max(len(docs),1)*1000:.1f}ms/doc")
    print("written to:       results/signals.jsonl, results/signals.db")
    high_impact = [s for s in signals if s.impact.score > 7]
    print(f"high-impact (>7): {len(high_impact)}")
    for s in sorted(signals, key=lambda s: -s.impact.score)[:5]:
        print(f"  impact={s.impact.score:.1f} event={s.event.event_class:20s} tickers={s.tickers} :: {s.text_preview[:80]}")


if __name__ == "__main__":
    main()
