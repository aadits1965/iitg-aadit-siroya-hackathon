"""Phase 4.6 hand-checkable unit tests: bond price vs closed-form, DV01 sign,
put monotonicity in spot, EL monotonicity in PD."""
from __future__ import annotations

from datetime import date

import pytest

from src.modules.stress_test.curve import MissingCurveCacheError, YieldCurve, load_curve, synthetic_test_only_curve
from src.modules.stress_test.pricing import (
    black_scholes,
    bond_price,
    expected_loss,
    price_interest_rate_swap,
    swap_dv01,
)


def flat_curve(rate: float) -> YieldCurve:
    # A single-point curve clamps zero_rate() to that one value at every
    # maturity (see YieldCurve.zero_rate), giving a perfectly flat curve.
    return YieldCurve(as_of=date(2026, 1, 1), rates_by_maturity_years={30.0: rate},
                       is_synthetic_test_only=True, source="test")


class TestBondPricing:
    def test_zero_coupon_matches_closed_form(self):
        curve = flat_curve(0.04)
        price = bond_price(face=100.0, coupon_rate=0.0, maturity_years=1.0, curve=curve, freq=2)
        expected = 100.0 / (1.02**2)
        assert price == pytest.approx(expected, rel=1e-9)

    def test_coupon_bond_matches_closed_form(self):
        curve = flat_curve(0.05)
        # 2-year, 6% annual coupon (3% semi), face 100, flat 5% curve.
        price = bond_price(face=100.0, coupon_rate=0.06, maturity_years=2.0, curve=curve, freq=2)
        df = lambda t: 1.0 / (1.025**(2 * t))
        expected = sum(3.0 * df(t) for t in [0.5, 1.0, 1.5, 2.0]) + 100.0 * df(2.0)
        assert price == pytest.approx(expected, rel=1e-9)

    def test_higher_spread_lowers_price(self):
        curve = flat_curve(0.04)
        p_no_spread = bond_price(face=100.0, coupon_rate=0.04, maturity_years=5.0, curve=curve, credit_spread_bp=0)
        p_with_spread = bond_price(face=100.0, coupon_rate=0.04, maturity_years=5.0, curve=curve, credit_spread_bp=200)
        assert p_with_spread < p_no_spread

    def test_par_bond_prices_at_par_when_coupon_equals_flat_rate(self):
        curve = flat_curve(0.04)
        price = bond_price(face=100.0, coupon_rate=0.04, maturity_years=10.0, curve=curve)
        assert price == pytest.approx(100.0, abs=0.05)


class TestSwapDV01:
    def test_payer_fixed_dv01_negative_under_rate_decrease(self):
        curve = flat_curve(0.04)
        dv01 = swap_dv01(notional=10_000_000, fixed_rate=0.04, maturity_years=5.0, curve=curve)
        assert dv01 < 0  # paying fixed loses value when rates fall

    def test_receiver_fixed_dv01_is_opposite_sign(self):
        curve = flat_curve(0.04)
        payer_dv01 = swap_dv01(notional=10_000_000, fixed_rate=0.04, maturity_years=5.0, curve=curve)
        receiver_dv01 = -payer_dv01
        assert receiver_dv01 > 0  # receiving fixed gains value when rates fall (like holding a bond)

    def test_atm_swap_value_near_zero(self):
        curve = flat_curve(0.04)
        result = price_interest_rate_swap(notional=10_000_000, fixed_rate=0.04, maturity_years=5.0, curve=curve)
        assert abs(result.value_payer_fixed) < 1000  # small relative to notional, at-market fixed rate


class TestBlackScholes:
    def test_put_value_rises_as_spot_falls(self):
        p_at_100 = black_scholes(spot=100, strike=100, maturity_years=1.0, risk_free_rate=0.04, volatility=0.25, option_type="put")
        p_at_90 = black_scholes(spot=90, strike=100, maturity_years=1.0, risk_free_rate=0.04, volatility=0.25, option_type="put")
        assert p_at_90.price > p_at_100.price

    def test_put_delta_is_negative(self):
        r = black_scholes(spot=100, strike=100, maturity_years=1.0, risk_free_rate=0.04, volatility=0.25, option_type="put")
        assert -1.0 <= r.delta <= 0.0

    def test_call_delta_is_positive(self):
        r = black_scholes(spot=100, strike=100, maturity_years=1.0, risk_free_rate=0.04, volatility=0.25, option_type="call")
        assert 0.0 <= r.delta <= 1.0

    def test_gamma_nonnegative(self):
        r = black_scholes(spot=100, strike=100, maturity_years=1.0, risk_free_rate=0.04, volatility=0.25, option_type="put")
        assert r.gamma >= 0.0


class TestCurveLoading:
    def test_missing_cache_raises_not_silently_falls_back(self, tmp_path):
        missing_path = tmp_path / "does_not_exist.csv"
        with pytest.raises(MissingCurveCacheError):
            load_curve(cache_path=missing_path)

    def test_synthetic_test_only_curve_is_clearly_flagged(self):
        c = synthetic_test_only_curve()
        assert c.is_synthetic_test_only is True
        assert "SYNTHETIC_TEST_ONLY" in c.source


class TestExpectedLoss:
    def test_monotonic_in_pd(self):
        el_low = expected_loss(ead=1_000_000, pd=0.01, lgd=0.45)
        el_high = expected_loss(ead=1_000_000, pd=0.05, lgd=0.45)
        assert el_high > el_low

    def test_zero_pd_zero_loss(self):
        assert expected_loss(ead=1_000_000, pd=0.0, lgd=0.45) == 0.0

    def test_matches_identity(self):
        assert expected_loss(ead=2_000_000, pd=0.02, lgd=0.4) == pytest.approx(2_000_000 * 0.02 * 0.4)
