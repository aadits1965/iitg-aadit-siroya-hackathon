#!/usr/bin/env python
"""Pull every source once and write cached snapshots to data/cache/ and
data/raw_samples/ for deterministic --demo runs: news (GDELT, core + widened
event-study universe), social (Mastodon live + Twitter-replay fallback), and
market data (US Treasury yield curve, equity prices, optional FRED spreads).

Run this from a normal network connection -- GDELT, Treasury, and Yahoo Finance
are all confirmed unreachable from the dev sandbox this project was built in
(shared/datacenter IP blocked -- see docs/DATA_VERIFICATION.md sections 8-9).

Expected runtime on a clean connection: ~15-20 minutes total, dominated by
GDELT's own 5-second self-throttle across ~100 queries (16 core + ~80 widened
event-study universe) and ~80 individual yfinance downloads.

Flags:
  --skip-event-study   skip the ~80-query widened GDELT pull (faster, but the
                        impact-score event study will stay underpowered)
  --skip-market-data    skip Treasury/yfinance/FRED (faster, but Module B will
                        have no curve to price against)
  --market-only         skip ALL news/social ingestion (GDELT, Mastodon,
                        Twitter replay) and fetch ONLY the Treasury curve
                        (direct, never provisional) + FRED spreads + equity
                        spot prices for Module B's option underlyings. Added
                        2026-10-18 after GDELT returned HTTP 429 on every
                        query for 2+ hours (0 articles) -- see
                        docs/ASSUMPTIONS.md "Impact-score event study: not
                        run". Use this if you just need a real, non-
                        provisional curve for Module B and GDELT is
                        unreachable/rate-limited.
"""
import argparse
import logging
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.ingestion.pipeline import build_all_caches, build_market_only_cache  # noqa: E402
from src.modules.stress_test.portfolio import load_portfolio  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

ROOT = Path(__file__).resolve().parents[1]
TREASURY_CACHE = ROOT / "data" / "cache" / "market" / "treasury_par_yield_curve.csv"
PORTFOLIO_PATH = ROOT / "data" / "synthetic" / "portfolio.csv"


def _is_provisional(path: Path) -> bool:
    if not path.exists():
        return False
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.startswith("#"):
                break
            if line.lstrip("#").strip() == "provisional: true":
                return True
    return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-event-study", action="store_true")
    parser.add_argument("--skip-market-data", action="store_true")
    parser.add_argument("--skip-provisional-check", action="store_true")
    parser.add_argument("--market-only", action="store_true",
                         help="skip all news/social ingestion; fetch only the Treasury curve + FRED + "
                              "the option underlyings' equity spot prices")
    args = parser.parse_args()

    if args.market_only:
        underlyings = sorted({
            p.extra["underlying"] for p in load_portfolio(PORTFOLIO_PATH) if p.asset_class == "option"
        })
        print(f"--market-only: fetching the Treasury curve directly + equity spot for {underlyings} "
              f"(Module B's option underlyings) + FRED (if FRED_API_KEY set). No GDELT/Mastodon/Twitter.\n")
        result = build_market_only_cache(underlyings)
        print("\n=== market-only fetch summary ===")
        for key, path in result.items():
            print(f"{key:16s} {'wrote ' + path if path else 'SKIPPED/FAILED (see log above)'}")
        if result["treasury_curve"] is None:
            sys.exit(1)
        sys.exit(0)

    if not args.skip_market_data and not args.skip_provisional_check and _is_provisional(TREASURY_CACHE):
        print("Existing cached market data is PROVISIONAL (fetched via an AI-assisted web-fetch tool, not a direct download).")
        print("Running scripts/verify_provisional_data.py first to check it against a direct fetch...\n")
        check = subprocess.run([sys.executable, str(ROOT / "scripts" / "verify_provisional_data.py")])
        print()
        if check.returncode != 0:
            print("Provisional data check reported a mismatch (see above) -- continuing to overwrite with "
                  "freshly, directly-fetched data now.\n")
        else:
            print("Provisional data confirmed accurate -- overwriting with a fresh, non-provisional fetch now.\n")

    stats = build_all_caches(
        include_event_study_gdelt=not args.skip_event_study,
        include_market_data=not args.skip_market_data,
    )
    print("\n=== Ingestion summary ===")
    for s in stats:
        print(f"{s.source:20s} fetched={s.fetched:4d}  kept={s.kept_after_dedup:4d}  "
              f"dropped_exact={s.dropped_exact:3d}  dropped_fuzzy={s.dropped_fuzzy:3d}")
    print("\nOutput files (if their step ran and succeeded):")
    print("  data/cache/news_gdelt.jsonl              -- core 20-ticker news (dashboard/Module B)")
    print("  data/cache/news_gdelt_event_study.jsonl   -- wide 80-ticker news (impact-score event study)")
    print("  data/cache/social_mastodon.jsonl          -- live social posts")
    print("  data/raw_samples/social_twitter_replay.jsonl -- offline replay fallback")
    print("  data/cache/market/treasury_par_yield_curve.csv -- Module B discount curve")
    print("  data/cache/market/equity_prices.csv       -- event-study + option-underlying prices")
    print("  data/cache/market/fred_series.csv         -- credit spreads (only if FRED_API_KEY set)")
    if not stats:
        print("\nNo sources returned data. Check network connectivity.")
        sys.exit(1)
