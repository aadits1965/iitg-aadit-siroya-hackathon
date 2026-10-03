"""Unit tests for the event-study mechanics using a mocked price fetcher (no
network) -- verifies the no-look-ahead date alignment and the abstention rule
below MIN_SAMPLE_FOR_CORRELATION, since a real large-n run needs the GDELT cache
(blocked in this dev sandbox -- see docs/DATA_VERIFICATION.md)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from src.eval.impact_event_study import (
    EventRecord,
    MIN_SAMPLE_FOR_CORRELATION,
    compute_abnormal_returns,
    first_tradeable_close_date,
    run_event_study,
)

UTC = timezone.utc


def _series(dates: list[str], values: list[float]) -> pd.Series:
    idx = pd.to_datetime(dates)
    return pd.Series(values, index=idx)


class FakePriceFetcher:
    """Deterministic prices: AAPL and SPY both flat except AAPL jumps +10% on
    2026-01-06 (a Tuesday) with SPY flat that day -> abnormal return should be +10%."""

    AAPL = _series(
        ["2026-01-02", "2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08"],
        [100.0, 100.0, 110.0, 110.0, 110.0],
    )
    SPY = _series(
        ["2026-01-02", "2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08"],
        [400.0, 400.0, 400.0, 400.0, 400.0],
    )

    def __call__(self, ticker, start, end):
        return self.AAPL if ticker == "AAPL" else self.SPY


class TestDateAlignment:
    def test_event_before_market_open_uses_same_day(self):
        trading_days = list(pd.to_datetime(["2026-01-05", "2026-01-06", "2026-01-07"]))
        event = datetime(2026, 1, 6, 8, 0, tzinfo=UTC)  # ~3am ET, well before 9:30am open
        d = first_tradeable_close_date(event, trading_days)
        assert d == trading_days[1]

    def test_event_after_market_close_uses_next_day(self):
        trading_days = list(pd.to_datetime(["2026-01-05", "2026-01-06", "2026-01-07"]))
        event = datetime(2026, 1, 6, 21, 0, tzinfo=UTC)  # ~4pm ET, after close
        d = first_tradeable_close_date(event, trading_days)
        assert d == trading_days[2]


class TestAbnormalReturn:
    def test_recovers_known_abnormal_return(self):
        rec = EventRecord(ticker="AAPL", event_time_utc=datetime(2026, 1, 5, 23, 0, tzinfo=UTC), impact_score=8.0)
        resolved = compute_abnormal_returns([rec], FakePriceFetcher())
        assert len(resolved) == 1
        _, ar = resolved[0]
        assert ar == pytest.approx(0.10, abs=1e-6)


class TestAbstentionBelowMinSample:
    def test_refuses_to_report_correlation_below_threshold(self):
        recs = [
            EventRecord(ticker="AAPL", event_time_utc=datetime(2026, 1, 5, 23, 0, tzinfo=UTC), impact_score=8.0)
        ]
        result = run_event_study(recs, FakePriceFetcher())
        assert result.n <= MIN_SAMPLE_FOR_CORRELATION
        assert result.spearman_r is None
        assert "below the minimum" in result.note
