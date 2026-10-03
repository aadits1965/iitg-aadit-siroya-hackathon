"""Phase 4.5: naive approximation error grows with shock size (convexity/gamma
effect) -- the required "vs naive approach" comparison, verified mechanically."""
from __future__ import annotations

from datetime import date

from src.modules.stress_test.curve import YieldCurve
from src.modules.stress_test.naive_approx import bond_full_vs_duration_only, option_full_vs_delta_only


def flat_curve(rate: float) -> YieldCurve:
    return YieldCurve(as_of=date(2026, 1, 1), rates_by_maturity_years={30.0: rate},
                       is_synthetic_test_only=True, source="test")


class TestBondDurationApprox:
    def test_small_shock_small_error(self):
        curve = flat_curve(0.04)
        results = bond_full_vs_duration_only(face=100, coupon_rate=0.04, maturity_years=10, curve=curve, shock_bps=[5])
        assert abs(results[0].error) < 0.05  # small shock -> duration approx nearly exact

    def test_error_grows_with_shock_size(self):
        curve = flat_curve(0.04)
        results = bond_full_vs_duration_only(
            face=100, coupon_rate=0.04, maturity_years=10, curve=curve, shock_bps=[10, 100, 300]
        )
        errors = [abs(r.error) for r in results]
        assert errors[0] < errors[1] < errors[2]  # monotonically growing convexity error

    def test_duration_only_misses_convexity_at_large_shock(self):
        curve = flat_curve(0.04)
        results = bond_full_vs_duration_only(face=100, coupon_rate=0.04, maturity_years=20, curve=curve, shock_bps=[-300])
        # a large rate DROP: bond convexity means the full-reprice gain exceeds the linear approx's gain
        assert results[0].full_reprice_value > results[0].naive_approx_value


class TestOptionDeltaApprox:
    def test_small_shock_small_error(self):
        results = option_full_vs_delta_only(
            spot=100, strike=100, maturity_years=1.0, risk_free_rate=0.04, volatility=0.25,
            option_type="put", spot_shocks_pct=[0.01],
        )
        assert abs(results[0].error) < 0.1

    def test_error_grows_with_shock_size(self):
        results = option_full_vs_delta_only(
            spot=100, strike=100, maturity_years=1.0, risk_free_rate=0.04, volatility=0.25,
            option_type="put", spot_shocks_pct=[0.02, 0.10, 0.30],
        )
        errors = [abs(r.error) for r in results]
        assert errors[0] < errors[1] < errors[2]

    def test_delta_only_misses_gamma_at_large_shock(self):
        results = option_full_vs_delta_only(
            spot=100, strike=100, maturity_years=1.0, risk_free_rate=0.04, volatility=0.25,
            option_type="put", spot_shocks_pct=[-0.30],
        )
        # gamma > 0 means full reprice value exceeds the linear (delta-only) approx on a big move either way
        assert results[0].full_reprice_value > results[0].naive_approx_value
