#!/usr/bin/env python
"""Phase 3.3: run the Impact Score event study against real, timestamped,
ticker-linked documents and merge the result into results/metrics.json.

Uses the WIDENED event-study universe (data/universe_event_study.csv, 80
tickers) for entity linking, and both the core and wide GDELT caches, to
maximise sample size -- the correlation test needs n>=200 for adequate power
(see docs/EVALUATION.md section 3). Only uses documents whose timestamp is
genuinely the original publish time -- excludes
src/ingestion/social_twitter_replay.py output (raw_meta.timestamp_is_synthetic).

Run `python scripts/build_cache.py` from a normal network first -- see
docs/USER_TODO.md for the exact commands and expected runtime.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.eval.impact_event_study import (  # noqa: E402
    EventRecord,
    make_cached_price_fetcher,
    run_event_study,
    yfinance_price_fetcher,
)
from src.ingestion.base import SourceAdapter  # noqa: E402
from src.nlp.engine import RiskEngine  # noqa: E402
from src.nlp.entity_linking import EntityLinker, load_universe  # noqa: E402
from src.nlp.sentiment import FinBertSentimentScorer  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
METRICS_PATH = ROOT / "results" / "metrics.json"
EQUITY_CACHE_PATH = ROOT / "data" / "cache" / "market" / "equity_prices.csv"


def load_real_timestamp_docs() -> list:
    docs = []
    for path in [
        ROOT / "data" / "cache" / "news_gdelt.jsonl",
        ROOT / "data" / "cache" / "news_gdelt_event_study.jsonl",
        ROOT / "data" / "cache" / "social_mastodon.jsonl",
    ]:
        if path.exists():
            batch = list(SourceAdapter._read_jsonl(path))
            print(f"loaded {len(batch)} docs from {path}")
            docs.extend(batch)
    return docs


def main():
    docs = load_real_timestamp_docs()
    if not docs:
        print("No real-timestamp cached documents found. Run scripts/build_cache.py from a normal network first.")
        sys.exit(1)

    wide_universe = load_universe(ROOT / "data" / "universe_event_study.csv")
    linker = EntityLinker(universe=wide_universe)
    scorer = FinBertSentimentScorer()
    engine = RiskEngine(sentiment_scorer=scorer, entity_linker=linker)
    signals = engine.build_signals(docs)

    records = []
    for sig in signals:
        if len(sig.tickers) != 1:
            continue  # only use single-ticker signals for clean attribution
        records.append(EventRecord(
            ticker=sig.tickers[0],
            event_time_utc=sig.created_at_utc,
            impact_score=sig.impact.score,
        ))

    print(f"{len(records)} single-ticker signals available for the event study "
          f"(out of {len(signals)} total signals from {len(docs)} docs).")

    if EQUITY_CACHE_PATH.exists():
        print(f"Using cached prices from {EQUITY_CACHE_PATH}")
        price_fetcher = make_cached_price_fetcher(EQUITY_CACHE_PATH)
    else:
        print("No cached equity prices found -- falling back to live yfinance (may be slow/unreliable).")
        price_fetcher = yfinance_price_fetcher

    result = run_event_study(records, price_fetcher)

    existing = {}
    if METRICS_PATH.exists():
        existing = json.loads(METRICS_PATH.read_text(encoding="utf-8"))
    existing["impact_score_event_study"] = {
        "n_candidate_signals": len(records),
        "n_resolved": result.n,
        "power_adequate": result.power_adequate,
        "spearman_r": result.spearman_r,
        "spearman_p": result.spearman_p,
        "ci95": list(result.ci95) if result.ci95 else None,
        "mean_abs_ar_by_impact_decile": result.mean_abs_ar_by_decile,
        "note": result.note,
    }
    METRICS_PATH.parent.mkdir(parents=True, exist_ok=True)
    METRICS_PATH.write_text(json.dumps(existing, indent=2), encoding="utf-8")

    print(json.dumps(existing["impact_score_event_study"], indent=2))
    print(f"\nWritten to {METRICS_PATH}")
    if not result.power_adequate:
        print(f"\nWARNING: n={result.n} is below the power threshold of 200. The number above is still written "
              f"to metrics.json (never suppressed), but report it with its CI, not as a point estimate, and say "
              f"plainly in the deck/README that it's underpowered.")


if __name__ == "__main__":
    main()
