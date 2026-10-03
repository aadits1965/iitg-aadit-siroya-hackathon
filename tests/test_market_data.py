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


def test_multirow_csv_uses_latest_row(tmp_path, monkeypatch):
    import src.ingestion.market_data as market_data

    earlier_row = "10/01/2026,4.00,4.00,4.00,4.00,4.00,4.00,4.40,4.80,4.90,5.00,5.10,5.20,5.60,5.60"
    csv_text = REAL_HEADER + "\n" + earlier_row + "\n" + REAL_ROW

    monkeypatch.setattr(market_data.requests, "get", lambda url, timeout: FakeResponse(csv_text))

    out_path = tmp_path / "curve.csv"
    fetch_treasury_curve(year=2026, out_path=out_path)
    curve = load_curve(cache_path=out_path)
    assert curve.as_of == date(2026, 10, 2)  # the later of the two rows, not the first
