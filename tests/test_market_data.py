"""Verifies the Treasury CSV parser against the REAL confirmed response format
(see src/ingestion/market_data.py module docstring -- fetched live via WebFetch
on 2026-10-04, since direct requests from this dev sandbox fail outright).
No network call in this test -- requests.get is monkeypatched."""
from __future__ import annotations

from datetime import date

import pytest

from src.ingestion.market_data import fetch_treasury_curve
from src.modules.stress_test.curve import load_curve

REAL_HEADER = (
    'Date,"1 Mo","1.5 Month","2 Mo","3 Mo","4 Mo","6 Mo","1 Yr","2 Yr","3 Yr",'
    '"5 Yr","7 Yr","10 Yr","20 Yr","30 Yr"'
)
REAL_ROW = "10/02/2026,4.04,4.09,4.11,4.19,4.26,4.27,4.46,4.83,4.96,5.06,5.17,5.28,5.67,5.63"


class FakeResponse:
    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        pass


def test_parses_real_confirmed_csv_format(tmp_path, monkeypatch):
    import src.ingestion.market_data as market_data

    def fake_get(url, timeout):
        return FakeResponse(REAL_HEADER + "\n" + REAL_ROW)

    monkeypatch.setattr(market_data.requests, "get", fake_get)

    out_path = tmp_path / "curve.csv"
    fetch_treasury_curve(year=2026, out_path=out_path)

    curve = load_curve(cache_path=out_path)
    assert curve.as_of == date(2026, 10, 2)
    assert curve.is_synthetic_test_only is False
    # 1 Yr column (value 4.46) -> 0.0446 at maturity_years=1.0
    assert curve.zero_rate(1.0) == pytest.approx(0.0446, abs=1e-6)
    # 10 Yr column (value 5.28) -> 0.0528 at maturity_years=10.0
    assert curve.zero_rate(10.0) == pytest.approx(0.0528, abs=1e-6)
    # 1 Mo column (value 4.04) -> 0.0404 at maturity_years=1/12
    assert curve.zero_rate(1 / 12) == pytest.approx(0.0404, abs=1e-6)


def test_multirow_csv_uses_latest_row_when_ascending(tmp_path, monkeypatch):
    import src.ingestion.market_data as market_data

    earlier_row = "10/01/2026,4.00,4.00,4.00,4.00,4.00,4.00,4.40,4.80,4.90,5.00,5.10,5.20,5.60,5.60"
    csv_text = REAL_HEADER + "\n" + earlier_row + "\n" + REAL_ROW  # oldest first, newest last

    monkeypatch.setattr(market_data.requests, "get", lambda url, timeout: FakeResponse(csv_text))

    out_path = tmp_path / "curve.csv"
    fetch_treasury_curve(year=2026, out_path=out_path)
    curve = load_curve(cache_path=out_path)
    assert curve.as_of == date(2026, 10, 2)  # the later of the two rows, not the first


def test_multirow_csv_uses_latest_row_when_descending(tmp_path, monkeypatch):
    """Bug found on a real local run: Treasury's actual annual CSV is sorted
    DESCENDING (newest first), not ascending. The old code assumed ascending
    and grabbed the last line, silently returning the YEAR'S FIRST business
    day (2026-01-02) as `as_of` instead of the latest -- this test fails
    against that old behavior and must keep passing regardless of row order."""
    import src.ingestion.market_data as market_data

    earlier_row = "01/02/2026,4.00,4.00,4.00,4.00,4.00,4.00,4.40,4.80,4.90,5.00,5.10,5.20,5.60,5.60"
    csv_text = REAL_HEADER + "\n" + REAL_ROW + "\n" + earlier_row  # newest first, oldest last

    monkeypatch.setattr(market_data.requests, "get", lambda url, timeout: FakeResponse(csv_text))

    out_path = tmp_path / "curve.csv"
    fetch_treasury_curve(year=2026, out_path=out_path)
    curve = load_curve(cache_path=out_path)
    assert curve.as_of == date(2026, 10, 2)  # the max date present, not the last row in the file
    assert curve.as_of == max(date(2026, 10, 2), date(2026, 1, 2)), "as_of must be the max date, by construction"


def test_as_of_is_always_the_max_date_regardless_of_row_order(tmp_path, monkeypatch):
    """Explicit regression guard: shuffle several out-of-order rows and assert
    as_of is the max of their dates, not whichever happens to be last in the
    file -- this is the exact bug class that produced the wrong curve."""
    import src.ingestion.market_data as market_data

    rows = [
        "03/15/2026,4.00,4.00,4.00,4.00,4.00,4.00,4.40,4.80,4.90,5.00,5.10,5.20,5.60,5.60",
        "01/02/2026,3.90,3.90,3.90,3.90,3.90,3.90,4.30,4.70,4.80,4.90,5.00,5.10,5.50,5.50",
        REAL_ROW,  # 10/02/2026 -- the actual max, deliberately placed in the middle
        "02/10/2026,3.95,3.95,3.95,3.95,3.95,3.95,4.35,4.75,4.85,4.95,5.05,5.15,5.55,5.55",
    ]
    csv_text = REAL_HEADER + "\n" + "\n".join(rows)

    monkeypatch.setattr(market_data.requests, "get", lambda url, timeout: FakeResponse(csv_text))

    out_path = tmp_path / "curve.csv"
    fetch_treasury_curve(year=2026, out_path=out_path)
    curve = load_curve(cache_path=out_path)
    assert curve.as_of == date(2026, 10, 2)
