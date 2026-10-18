"""Market-data fetchers for Module B: US Treasury par yield curve, equity daily
prices (yfinance), and FRED credit-spread series. Meant to be run by
scripts/build_cache.py from a normal network -- confirmed unreachable via direct
requests from this dev sandbox (treasury.gov: HTTP 000 connection failure;
yfinance: JSON decode errors -- see docs/DATA_VERIFICATION.md section 9).

Treasury CSV column format confirmed live (via an AI-assisted web-fetch tool,
which reached the endpoint this sandbox's direct requests could not) on 2026-10-04:
    Date,"1 Mo","1.5 Month","2 Mo","3 Mo","4 Mo","6 Mo","1 Yr","2 Yr","3 Yr",
    "5 Yr","7 Yr","10 Yr","20 Yr","30 Yr"
    10/02/2026,4.04,4.09,4.11,4.19,4.26,4.27,4.46,4.83,4.96,5.06,5.17,5.28,5.67,5.63
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
MARKET_CACHE_DIR = ROOT / "data" / "cache" / "market"

TREASURY_CSV_URL = (
    "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/"
    "daily-treasury-rates.csv/{year}/all?type=daily_treasury_yield_curve&field_tdr_date_value={year}&page&_format=csv"
)

# Maps a Treasury header label to maturity in years. Built from the confirmed
# real header above -- not guessed.
_MATURITY_LABEL_PATTERN = re.compile(r"([\d.]+)\s*(Mo|Month|Yr)", re.IGNORECASE)


def _label_to_years(label: str) -> float | None:
    m = _MATURITY_LABEL_PATTERN.search(label)
    if not m:
        return None
    value, unit = float(m.group(1)), m.group(2).lower()
    return value / 12.0 if unit.startswith("mo") else value


def fetch_treasury_curve(year: int | None = None, out_path: Path | None = None) -> Path:
    """Fetches the full year's daily par yield curve CSV and writes only the
    MOST RECENT row (the latest available as-of date) in the format
    src/modules/stress_test/curve.py expects.

    Bug found on a real local run (2026-10-18/19): this used to grab
    `lines[-1]` on the assumption the file is sorted ascending by date (oldest
    first) -- but Treasury's CSV is actually sorted DESCENDING (newest first),
    so `lines[-1]` was the YEAR'S FIRST business day (2026-01-02), not the
    latest. Fixed by parsing every data row's date and picking the max,
    regardless of file order -- never assume sort order from an external
    source. See docs/ASSUMPTIONS.md "Treasury curve as_of bug"."""
    year = year or date.today().year
    out_path = out_path or (MARKET_CACHE_DIR / "treasury_par_yield_curve.csv")

    url = TREASURY_CSV_URL.format(year=year)
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    lines = resp.text.strip().splitlines()
    if len(lines) < 2:
        raise RuntimeError(f"Treasury CSV at {url} had no data rows")

    header = next(csv_row for csv_row in [lines[0]])
    import csv as _csv
    header_fields = next(_csv.reader([header]))
    maturity_cols = [(i, _label_to_years(h)) for i, h in enumerate(header_fields) if _label_to_years(h) is not None]
    if not maturity_cols:
        raise RuntimeError(f"Could not parse any maturity columns from Treasury header: {header_fields}")

    data_rows = [next(_csv.reader([line])) for line in lines[1:] if line.strip()]
    parsed_rows = [(datetime.strptime(row[0], "%m/%d/%Y").date(), row) for row in data_rows]
    as_of, last_row = max(parsed_rows, key=lambda t: t[0])

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        f.write(f"# as_of: {as_of.isoformat()}\n")
        f.write(f"# US Treasury daily par yield curve (home.treasury.gov), fetched directly via "
                f"scripts/build_cache.py on {date.today().isoformat()}\n")
        f.write(f"# raw source row: {','.join(last_row)}\n")
        f.write("maturity_years,par_yield\n")
        for col_idx, years in maturity_cols:
            pct = float(last_row[col_idx])
            f.write(f"{years:.10g},{pct / 100.0:.6f}\n")

    logger.info("wrote Treasury curve as_of=%s (most recent of %d rows parsed) to %s",
                as_of, len(parsed_rows), out_path)
    return out_path


def fetch_equity_prices(tickers: list[str], start: date, end: date, out_path: Path | None = None) -> Path:
    """Daily close prices for tickers (+ SPY, always included for the event
    study's market-return benchmark) via yfinance, written long-format."""
    import pandas as pd
    import yfinance as yf

    out_path = out_path or (MARKET_CACHE_DIR / "equity_prices.csv")
    all_tickers = sorted(set(tickers) | {"SPY"})

    rows = []
    for ticker in all_tickers:
        df = yf.download(ticker, start=start, end=end, progress=False, auto_adjust=True)
        if df is None or df.empty:
            logger.warning("no data returned for %s", ticker)
            continue
        close = df["Close"]
        if hasattr(close, "squeeze"):
            close = close.squeeze()
        for dt, px in close.items():
            rows.append((pd.Timestamp(dt).date().isoformat(), ticker, float(px)))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        f.write(f"# source: Yahoo Finance via yfinance, fetched directly via scripts/build_cache.py on "
                f"{date.today().isoformat()}\n")
        f.write("date,ticker,close\n")
        for d, t, px in rows:
            f.write(f"{d},{t},{px:.6f}\n")

    logger.info("wrote %d equity price rows (%d tickers) to %s", len(rows), len(all_tickers), out_path)
    return out_path


def fetch_fred_series(series_ids: list[str], api_key: str, out_path: Path | None = None) -> Path:
    """Credit-spread series (e.g. BAMLH0A0HYM2, BAMLC0A0CM) from FRED. Requires
    a free API key (set FRED_API_KEY in .env) -- see docs/DATA_VERIFICATION.md."""
    out_path = out_path or (MARKET_CACHE_DIR / "fred_series.csv")
    rows = []
    for series_id in series_ids:
        resp = requests.get(
            "https://api.stlouisfed.org/fred/series/observations",
            params={"series_id": series_id, "api_key": api_key, "file_type": "json"},
            timeout=20,
        )
        resp.raise_for_status()
        for obs in resp.json().get("observations", []):
            if obs["value"] == ".":
                continue
            rows.append((series_id, obs["date"], float(obs["value"])))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        f.write(f"# source: FRED (api.stlouisfed.org), fetched directly via scripts/build_cache.py on "
                f"{date.today().isoformat()}\n")
        f.write("series_id,date,value\n")
        for sid, d, v in rows:
            f.write(f"{sid},{d},{v}\n")

    logger.info("wrote %d FRED observation rows to %s", len(rows), out_path)
    return out_path
