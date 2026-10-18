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
limitations wherever this result is reported (README/deck).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import numpy as np
from scipy.stats import spearmanr

MARKET_TZ = ZoneInfo("America/New_York")
MARKET_CLOSE_HOUR = 16  # 4pm ET

# Power-based threshold, not an arbitrary round number: detecting a modest
# correlation (r~=0.2, the kind of effect size plausible for a single rule-based
# severity score against noisy daily abnormal returns) at 80% power needs n~=194
# (two-sided alpha=0.05; derived from the standard Fisher z-transform sample-size
# formula for a Pearson/Spearman correlation test). At n=30 the 95% CI for an
# observed r=0.2 is roughly [-0.17, 0.52] -- wide enough to be uninformative.
MIN_SAMPLE_FOR_POWER = 200


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
    power_adequate: bool
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
    power_adequate = n >= MIN_SAMPLE_FOR_POWER

    if n < 3:
        return EventStudyResult(
            n=n,
            spearman_r=None,
            spearman_p=None,
            ci95=None,
            mean_abs_ar_by_decile=None,
            power_adequate=False,
            note=(
                f"n={n} resolved events -- too few to compute a correlation or a bootstrap CI at all "
                "(need at least 3 points). No number is reported."
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

    power_note = (
        f"n={n} meets the n>={MIN_SAMPLE_FOR_POWER} threshold for ~80% power to detect r~=0.2 at alpha=0.05."
        if power_adequate else
        f"UNDERPOWERED: n={n} is below the n>={MIN_SAMPLE_FOR_POWER} threshold for ~80% power to detect "
        f"r~=0.2. The point estimate and CI below are reported as computed, but this sample size cannot "
        f"reliably distinguish a real small-to-moderate correlation from noise -- treat the wide CI as the "
        f"headline, not the point estimate."
    )
    return EventStudyResult(
        n=n,
        spearman_r=float(r),
        spearman_p=float(p),
        ci95=(float(lo), float(hi)),
        mean_abs_ar_by_decile=mean_by_decile,
        power_adequate=power_adequate,
        note=power_note + " Association only, not causation. Confounders (earnings dates, market-wide days, "
             "multiple same-day news items per ticker) are not controlled for.",
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


def make_cached_price_fetcher(cache_path):
    """Reads data/cache/market/equity_prices.csv (built by
    scripts/build_cache.py / src/ingestion/market_data.py) instead of calling
    yfinance live -- keeps the event study reproducible/offline once the cache
    exists. Returns None for a ticker/window with no cached coverage, so the
    caller falls back to live yfinance for that one ticker rather than failing
    the whole run."""
    import pandas as pd

    df = pd.read_csv(cache_path, comment="#")
    df["date"] = pd.to_datetime(df["date"])

    def fetcher(ticker: str, start: datetime, end: datetime):
        sub = df[(df["ticker"] == ticker) & (df["date"] >= pd.Timestamp(start.date())) & (df["date"] <= pd.Timestamp(end.date()))]
        if sub.empty:
            return None
        return sub.set_index("date")["close"]

    return fetcher
