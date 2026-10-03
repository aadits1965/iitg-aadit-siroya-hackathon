#!/usr/bin/env python
"""Phase 3.3: run the Impact Score event study against real, timestamped,
ticker-linked documents and merge the result into results/metrics.json.

Only uses documents whose timestamp is genuinely the original publish time --
excludes src/ingestion/social_twitter_replay.py output (raw_meta.timestamp_is_synthetic),
per docs/DATA_VERIFICATION.md. In practice this means GDELT news + live Mastodon
posts. Run `python scripts/build_cache.py` from a normal network first so
data/cache/news_gdelt.jsonl exists -- see docs/USER_TODO.md.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.eval.impact_event_study import EventRecord, run_event_study, yfinance_price_fetcher  # noqa: E402
from src.ingestion.base import SourceAdapter  # noqa: E402
from src.nlp.engine import RiskEngine  # noqa: E402
from src.nlp.entity_linking import EntityLinker  # noqa: E402
from src.nlp.sentiment import FinBertSentimentScorer  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
METRICS_PATH = ROOT / "results" / "metrics.json"


def load_real_timestamp_docs() -> list:
    docs = []
    for path in [ROOT / "data" / "cache" / "news_gdelt.jsonl", ROOT / "data" / "cache" / "social_mastodon.jsonl"]:
        if path.exists():
            docs.extend(list(SourceAdapter._read_jsonl(path)))
    return docs


def main():
    docs = load_real_timestamp_docs()
    if not docs:
        print("No real-timestamp cached documents found (need data/cache/news_gdelt.jsonl and/or "
              "data/cache/social_mastodon.jsonl). Run scripts/build_cache.py from a normal network first.")
        sys.exit(1)

    linker = EntityLinker()
    scorer = FinBertSentimentScorer()
    engine = RiskEngine(sentiment_scorer=scorer, entity_linker=linker)
    signals = engine.build_signals(docs)

    records = []
    for sig in signals:
        if len(sig.tickers) != 1:
            continue  # only use single-ticker signals for clean attribution
        records.append(EventRecord(
            ticker=sig.tickers[0],
            event_time_utc=sig.created_at_utc,  # cluster's representative time; see engine.py
            impact_score=sig.impact.score,
        ))

    print(f"{len(records)} single-ticker signals available for the event study "
          f"(out of {len(signals)} total signals from {len(docs)} docs).")

    result = run_event_study(records, yfinance_price_fetcher)

    existing = {}
    if METRICS_PATH.exists():
        existing = json.loads(METRICS_PATH.read_text(encoding="utf-8"))
    existing["impact_score_event_study"] = {
        "n_candidate_signals": len(records),
        "n_resolved": result.n,
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


if __name__ == "__main__":
    main()
