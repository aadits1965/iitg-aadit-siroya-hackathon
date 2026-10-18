#!/usr/bin/env python
"""Cross-checks the PROVISIONAL market-data snapshots (fetched via an
AI-assisted web-fetch tool, which passes content through a summarising model --
see docs/DATA_VERIFICATION.md section 9) against a direct, un-summarised
download, and reports any differences. Run this from a normal network (this
dev sandbox's direct requests to treasury.gov/Yahoo Finance fail outright).

Nothing from the provisional snapshot should go into the deck/README/final
numbers until this check passes -- if it reports any MISMATCH, investigate
before trusting results/stress_test_output.json or anything derived from it.
"""
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.ingestion.market_data import fetch_equity_prices, fetch_treasury_curve  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
PROVISIONAL_CURVE = ROOT / "data" / "cache" / "market" / "treasury_par_yield_curve.csv"
PROVISIONAL_EQUITY = ROOT / "data" / "cache" / "market" / "equity_prices.csv"
TOLERANCE = 0.0005  # 5bp for yields (decimal), $0.01-scale for prices handled separately


def read_curve_csv(path: Path) -> dict[float, float]:
    rates = {}
    with path.open("r", encoding="utf-8") as f:
        lines = [l for l in f if not l.startswith("#")]
    for row in csv.DictReader(lines):
        rates[float(row["maturity_years"])] = float(row["par_yield"])
    return rates


def read_equity_csv(path: Path) -> dict[tuple[str, str], float]:
    prices = {}
    with path.open("r", encoding="utf-8") as f:
        lines = [l for l in f if not l.startswith("#")]
    for row in csv.DictReader(lines):
        prices[(row["ticker"], row["date"])] = float(row["close"])
    return prices


def main():
    print("=== Verifying Treasury par yield curve ===")
    provisional_rates = read_curve_csv(PROVISIONAL_CURVE)
    tmp_curve_path = ROOT / "data" / "cache" / "market" / "_verify_treasury.csv"
    fetch_treasury_curve(out_path=tmp_curve_path)
    direct_rates = read_curve_csv(tmp_curve_path)

    mismatches = []
    for maturity, prov_val in provisional_rates.items():
        direct_val = direct_rates.get(maturity)
        if direct_val is None:
            mismatches.append(f"  maturity={maturity}: provisional has it, direct fetch does not (different date?)")
        elif abs(direct_val - prov_val) > TOLERANCE:
            mismatches.append(f"  maturity={maturity}: provisional={prov_val:.4%} vs direct={direct_val:.4%} "
                               f"(diff {abs(direct_val-prov_val)*10000:.1f}bp)")

    if mismatches:
        print("MISMATCH found in Treasury curve:")
        print("\n".join(mismatches))
        print("\nNote: a mismatch may simply mean the date has moved on (markets are open daily) -- "
              "compare the '# as_of:' date in both files before concluding it's a transcription error.")
    else:
        print(f"MATCH: all {len(provisional_rates)} maturities agree within {TOLERANCE*10000:.0f}bp.")

    print("\n=== Verifying equity prices ===")
    provisional_prices = read_equity_csv(PROVISIONAL_EQUITY)
    tickers = sorted({t for t, _ in provisional_prices})
    tmp_equity_path = ROOT / "data" / "cache" / "market" / "_verify_equity.csv"
    fetch_equity_prices(tickers, start=__import__("datetime").date.today() - __import__("datetime").timedelta(days=7),
                         end=__import__("datetime").date.today(), out_path=tmp_equity_path)
    direct_prices = read_equity_csv(tmp_equity_path)

    equity_mismatches = []
    for (ticker, d), prov_px in provisional_prices.items():
        direct_px = direct_prices.get((ticker, d))
        if direct_px is None:
            equity_mismatches.append(f"  {ticker} {d}: provisional has it, direct fetch does not (different trading day?)")
        elif abs(direct_px - prov_px) / prov_px > 0.001:  # 0.1% tolerance
            equity_mismatches.append(f"  {ticker} {d}: provisional=${prov_px:.2f} vs direct=${direct_px:.2f} "
                                      f"(diff {abs(direct_px-prov_px)/prov_px*100:.2f}%)")

    if equity_mismatches:
        print("MISMATCH found in equity prices:")
        print("\n".join(equity_mismatches))
    else:
        print(f"MATCH: all {len(provisional_prices)} provisional price points agree within 0.1%.")

    print("\n=== Next step ===")
    if not mismatches and not equity_mismatches:
        print("All provisional data confirmed accurate. Run `python scripts/build_cache.py` to replace the "
              "provisional files with fresh, directly-fetched (non-provisional) ones, then re-run "
              "`python scripts/run_stress_test.py` before using any number in the deck/README.")
        sys.exit(0)
    else:
        print("Discrepancies found above -- do NOT use the current provisional numbers in the deck/README "
              "until resolved. Run `python scripts/build_cache.py` to replace them with directly-fetched data.")
        sys.exit(1)


if __name__ == "__main__":
    main()
