"""Discount curve: loads a dated US Treasury par-yield snapshot and provides
linear-interpolated zero rates for discounting cashflows at arbitrary maturities.

Real snapshots are written to CACHE_PATH by scripts/build_cache.py (meant to be
run from a normal network -- this dev sandbox's direct network calls to
treasury.gov fail outright, HTTP code 000; see docs/DATA_VERIFICATION.md
section 9). `load_curve()` reads ONLY that cache file and **raises** if it is
missing -- there is no silent fallback. The only synthetic curve in this module
is `synthetic_test_only_curve()`, which is never called by `load_curve()` and
must never be wired into any production path (dashboard, deck, metrics.json) --
tests use it explicitly and by name so that is always visible in a diff/review.

**Provisional data:** a curve fetched via an AI-assisted web-fetch tool (which
passes page content through a summarising model rather than returning raw
bytes) is marked `is_provisional=True` (a `# provisional: true` line in the
cache file) until `scripts/verify_provisional_data.py` confirms it against a
directly-downloaded copy -- so despite being real, live-fetched data (not
fabricated), it isn't treated as final until verified. Callers that produce
deck/README-facing output should check `curve.is_provisional` and refuse/warn
accordingly -- see scripts/run_stress_test.py for the pattern. (The currently
cached curve is a direct fetch, not provisional -- see
`src/ingestion/market_data.py::fetch_treasury_curve()`.)
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import numpy as np

CACHE_PATH = Path(__file__).resolve().parents[3] / "data" / "cache" / "market" / "treasury_par_yield_curve.csv"


@dataclass
class YieldCurve:
    as_of: date
    rates_by_maturity_years: dict[float, float]  # par yield, decimal (0.04 = 4%)
    is_synthetic_test_only: bool
    source: str
    is_provisional: bool = False
    """True when this snapshot was fetched via an AI-assisted web-fetch tool
    that passes content through a summarising model rather than a direct
    byte-for-byte download -- see docs/DATA_VERIFICATION.md section 9.
    Provisional data must never be used in the deck/README/final numbers
    until scripts/verify_provisional_data.py confirms it against a direct
    fetch."""

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
        return YieldCurve(as_of=self.as_of, rates_by_maturity_years=new_rates,
                           is_synthetic_test_only=self.is_synthetic_test_only, source=self.source + " +shock",
                           is_provisional=self.is_provisional)


class MissingCurveCacheError(RuntimeError):
    pass


def load_curve(cache_path: Path = CACHE_PATH) -> YieldCurve:
    """Real data only. Raises MissingCurveCacheError if the cache hasn't been
    built yet -- callers (revaluation scripts, the dashboard) must not catch
    this and silently substitute a synthetic curve; run
    `python scripts/build_cache.py` once to fetch the real curve first."""
    if not cache_path.exists():
        raise MissingCurveCacheError(
            f"{cache_path} not found. Run `python scripts/build_cache.py` (from a normal network -- "
            "treasury.gov is unreachable from the dev sandbox, see docs/DATA_VERIFICATION.md section 9) "
            "to fetch a real dated yield curve snapshot before running Module B."
        )

    as_of = None
    is_provisional = False
    source_lines = []
    rates: dict[float, float] = {}
    with cache_path.open("r", encoding="utf-8") as f:
        lines = f.readlines()

    header_idx = 0
    for i, line in enumerate(lines):
        if line.startswith("#"):
            stripped = line.lstrip("#").strip()
            if stripped.startswith("as_of:"):
                as_of = datetime.strptime(stripped.split(":", 1)[1].strip(), "%Y-%m-%d").date()
            elif stripped.startswith("provisional:"):
                is_provisional = stripped.split(":", 1)[1].strip().lower() == "true"
            else:
                source_lines.append(stripped)
            header_idx = i + 1
        else:
            break

    reader = csv.DictReader(lines[header_idx:])
    for row in reader:
        rates[float(row["maturity_years"])] = float(row["par_yield"])

    if as_of is None or not rates:
        raise MissingCurveCacheError(f"{cache_path} exists but is malformed (missing '# as_of:' header or rows).")

    return YieldCurve(
        as_of=as_of,
        rates_by_maturity_years=rates,
        is_synthetic_test_only=False,
        is_provisional=is_provisional,
        source=" | ".join(source_lines) or f"cached from {cache_path.name}",
    )


def synthetic_test_only_curve() -> YieldCurve:
    """A clearly-labelled, non-real curve for unit tests ONLY. Never call this
    from a revaluation/dashboard/deck/metrics code path -- `is_synthetic_test_only`
    is set so any accidental use is easy to assert against and catch in review."""
    return YieldCurve(
        as_of=date(1970, 1, 1),
        rates_by_maturity_years={
            1 / 12: 0.0430, 2 / 12: 0.0428, 3 / 12: 0.0425, 6 / 12: 0.0415,
            1.0: 0.0400, 2.0: 0.0385, 3.0: 0.0378, 5.0: 0.0375,
            7.0: 0.0380, 10.0: 0.0390, 20.0: 0.0420, 30.0: 0.0430,
        },
        is_synthetic_test_only=True,
        source="SYNTHETIC_TEST_ONLY -- illustrative numbers, not a real dated quote. Must never appear in "
               "results/metrics.json, the dashboard, or the deck.",
    )
