"""Discount curve: loads a dated US Treasury par-yield snapshot and provides
linear-interpolated zero rates for discounting cashflows at arbitrary maturities.

Real snapshots are fetched by scripts/build_market_data_cache.py (requires
network access this dev sandbox does not currently have to treasury.gov --
confirmed via a direct connection test, HTTP code 000 / connection failure, as
opposed to GDELT's HTTP 429 -- see docs/DATA_VERIFICATION.md). Until that cache
exists, FALLBACK_CURVE below is used, and every object built from it is tagged
`is_fallback=True` so no downstream output can silently claim to be real market
data. FALLBACK_CURVE's values are a clearly-labelled illustrative curve, not a
quote from any dated real snapshot.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import numpy as np

CACHE_PATH = Path(__file__).resolve().parents[3] / "data" / "cache" / "market" / "treasury_par_yield_curve.csv"

# Illustrative only -- NOT a real quoted curve. Roughly curve-shaped (short rates
# below long rates) purely so pricing math has believable-looking but clearly
# non-authoritative numbers to run against before a real snapshot is cached.
FALLBACK_CURVE = {
    1 / 12: 0.0430, 2 / 12: 0.0428, 3 / 12: 0.0425, 6 / 12: 0.0415,
    1.0: 0.0400, 2.0: 0.0385, 3.0: 0.0378, 5.0: 0.0375,
    7.0: 0.0380, 10.0: 0.0390, 20.0: 0.0420, 30.0: 0.0430,
}


@dataclass
class YieldCurve:
    as_of: date
    rates_by_maturity_years: dict[float, float]  # par yield, decimal (0.04 = 4%)
    is_fallback: bool = False
    source: str = ""

    def zero_rate(self, maturity_years: float) -> float:
        """Linear interpolation on the par curve, used as a zero-rate proxy.
        A simplification (no proper bootstrapping) -- stated in docs/ASSUMPTIONS.md."""
        maturities = sorted(self.rates_by_maturity_years)
        if maturity_years <= maturities[0]:
            return self.rates_by_maturity_years[maturities[0]]
        if maturity_years >= maturities[-1]:
            return self.rates_by_maturity_years[maturities[-1]]
        return float(np.interp(maturity_years, maturities, [self.rates_by_maturity_years[m] for m in maturities]))

    def discount_factor(self, maturity_years: float) -> float:
        r = self.zero_rate(maturity_years)
        return 1.0 / ((1.0 + r / 2.0) ** (2.0 * maturity_years))  # semi-annual compounding, standard for USTs

    def shocked(self, parallel_bp: float = 0.0, steepener_bp_per_10y: float = 0.0) -> "YieldCurve":
        """Apply a parallel shift (bp) plus an optional steepener (extra bp per
        10y of maturity, added on top of the parallel shift)."""
        new_rates = {}
        for m, r in self.rates_by_maturity_years.items():
            shift = parallel_bp / 10000.0 + (steepener_bp_per_10y / 10000.0) * (m / 10.0)
            new_rates[m] = r + shift
        return YieldCurve(as_of=self.as_of, rates_by_maturity_years=new_rates, is_fallback=self.is_fallback,
                           source=self.source + " +shock")


def load_curve() -> YieldCurve:
    if CACHE_PATH.exists():
        rows = []
        with CACHE_PATH.open("r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                rows.append((float(row["maturity_years"]), float(row["par_yield"])))
        as_of_str = CACHE_PATH.read_text(encoding="utf-8").splitlines()[0]
        return YieldCurve(
            as_of=date.today(),
            rates_by_maturity_years=dict(rows),
            is_fallback=False,
            source=f"US Treasury daily par yield curve, cached from {CACHE_PATH.name}",
        )
    return YieldCurve(
        as_of=date.today(),
        rates_by_maturity_years=dict(FALLBACK_CURVE),
        is_fallback=True,
        source="FALLBACK_CURVE (illustrative, not a real dated quote -- see module docstring)",
    )
