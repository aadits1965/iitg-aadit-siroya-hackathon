"""Phase 3.3: validate the Impact Score against realised market moves (event
study). Needs real, timestamped news linked to a ticker -- the tweet-replay
dataset has no timestamps (confirmed, see docs/DATA_VERIFICATION.md) so it is
never used here; this runs on GDELT-sourced signals only, or any other signal
whose underlying documents carry a genuine (non-synthetic) timestamp.

Method: for each (ticker, event_time, impact_score) triple, find the first
trading day D whose *entire session* occurs after event_time (so the news is
fully "in the price" before the return window starts -- no look-ahead), and
compute abnormal return AR = stock_return[D] - SPY_return[D] using close-to-
close returns. Report Spearman correlation between Impact Score and |AR| with
a bootstrap 95% CI, plus mean |AR| by impact decile. This is an association
test, not a causal claim -- confounders (earnings dates, market-wide moves,
multiple news items per day) are not controlled for and are stated as
limitations wherever this result is reported (README/deck/QA_PREP).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import numpy as np
from scipy.stats import spearmanr

MARKET_TZ = ZoneInfo("America/New_York")
MARKET_CLOSE_HOUR = 16  # 4pm ET
MIN_SAMPLE_FOR_CORRELATION = 30  # below this, a correlation number is not meaningful -- refuse to report one


@dataclass
class EventRecord:
    ticker: str
    event_time_utc: datetime
    impact_score: float


@dataclass
class EventStudyResult:
    n: int
    spearman_r: float | None
    spearman_p: float | None
    ci95: tuple[float, float] | None
    mean_abs_ar_by_decile: list[float] | None
    note: str


def first_tradeable_close_date(event_time_utc: datetime, trading_days: list) -> "object | None":
    """trading_days: sorted list of pandas Timestamps (date-normalised, tz-naive,
    representing each available trading day in the price series). Returns the
    first trading day whose full session starts after event_time (i.e. event
    happened before that day's market open, so no look-ahead)."""
    event_local = event_time_utc.astimezone(MARKET_TZ)
    for d in trading_days:
        # Treat each trading day's session as starting 9:30am ET; if the event
        # happened before that, this day's return is "clean" (post-news).
        day_open = datetime(d.year, d.month, d.day, 9, 30, tzinfo=MARKET_TZ)
        if event_local < day_open:
            return d
    return None


def compute_abnormal_returns(records: list[EventRecord], price_fetcher) -> list[tuple[EventRecord, float]]:
    """price_fetcher(ticker, start, end) -> pandas Series of daily close prices,
    indexed by tz-naive date. Injected so this is unit-testable without network.
    Returns (record, abnormal_return) for every record that could be resolved."""
    results = []
    spy_cache = {}

    for rec in records:
        start = rec.event_time_utc - timedelta(days=3)
        end = rec.event_time_utc + timedelta(days=10)

        stock_px = price_fetcher(rec.ticker, start, end)
        if stock_px is None or len(stock_px) < 2:
            continue

        key = (start.date(), end.date())
        spy_px = spy_cache.get(key)
        if spy_px is None:
            spy_px = price_fetcher("SPY", start, end)
            spy_cache[key] = spy_px
        if spy_px is None or len(spy_px) < 2:
            continue

        trading_days = sorted(stock_px.index)
        d = first_tradeable_close_date(rec.event_time_utc, trading_days)
        if d is None:
            continue
        idx = trading_days.index(d)
        if idx == 0:
            continue  # need a prior close to compute a return
        d_prev = trading_days[idx - 1]

        if d not in spy_px.index or d_prev not in spy_px.index:
            continue

        stock_ret = stock_px[d] / stock_px[d_prev] - 1.0
        spy_ret = spy_px[d] / spy_px[d_prev] - 1.0
        ar = float(stock_ret - spy_ret)
        results.append((rec, ar))

    return results


def run_event_study(records: list[EventRecord], price_fetcher) -> EventStudyResult:
    resolved = compute_abnormal_returns(records, price_fetcher)
    n = len(resolved)

    if n < MIN_SAMPLE_FOR_CORRELATION:
        return EventStudyResult(
            n=n,
            spearman_r=None,
            spearman_p=None,
            ci95=None,
            mean_abs_ar_by_decile=None,
            note=(
                f"n={n} resolved events, below the minimum of {MIN_SAMPLE_FOR_CORRELATION} this project "
                "treats as meaningful for a correlation estimate. No correlation number is reported -- "
                "reporting one at this sample size would be noise presented as signal."
            ),
        )

    impacts = np.array([r.impact_score for r, _ in resolved])
    abs_ars = np.array([abs(ar) for _, ar in resolved])

    r, p = spearmanr(impacts, abs_ars)

    rng = np.random.default_rng(42)
    boot = []
    for _ in range(2000):
        idx = rng.integers(0, n, n)
        rb, _ = spearmanr(impacts[idx], abs_ars[idx])
        if not np.isnan(rb):
            boot.append(rb)
    lo, hi = (np.percentile(boot, [2.5, 97.5]) if boot else (float("nan"), float("nan")))

    deciles = np.clip((np.argsort(np.argsort(impacts)) * 10 // n), 0, 9)
    mean_by_decile = [float(abs_ars[deciles == k].mean()) if (deciles == k).any() else float("nan") for k in range(10)]

    return EventStudyResult(
        n=n,
        spearman_r=float(r),
        spearman_p=float(p),
        ci95=(float(lo), float(hi)),
        mean_abs_ar_by_decile=mean_by_decile,
        note="Association only, not causation. Confounders (earnings dates, market-wide days, multiple "
             "same-day news items per ticker) are not controlled for.",
    )


def yfinance_price_fetcher(ticker: str, start: datetime, end: datetime):
    import pandas as pd
    import yfinance as yf

    df = yf.download(ticker, start=start.date(), end=end.date(), progress=False, auto_adjust=True)
    if df is None or df.empty:
        return None
    close = df["Close"]
    if hasattr(close, "squeeze"):
        close = close.squeeze()
    close.index = pd.to_datetime(close.index).tz_localize(None).normalize()
    return close
