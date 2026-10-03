"""Phase 4.5: full reprice vs naive first-order approximation (duration-only for
rate-sensitive instruments, delta-only for options), across shock sizes. The
point is to measure a REAL difference -- both methods are implemented properly
(see pricing.py), so the gap reported here is genuine convexity/gamma error,
not an artifact of two versions of the same shortcut."""
from __future__ import annotations

from dataclasses import dataclass

from src.modules.stress_test.curve import YieldCurve
from src.modules.stress_test.pricing import black_scholes, bond_price


@dataclass
class ApproxComparison:
    shock_label: str
    full_reprice_value: float
    naive_approx_value: float

    @property
    def error(self) -> float:
        return self.naive_approx_value - self.full_reprice_value

    @property
    def error_pct_of_full_move(self) -> float:
        full_move = self.full_reprice_value
        return abs(self.error) / abs(full_move) if abs(full_move) > 1e-9 else float("nan")


def effective_duration(face: float, coupon_rate: float, maturity_years: float, curve: YieldCurve, credit_spread_bp: float = 0.0, bump_bp: float = 1.0) -> float:
    """Numerically-estimated effective duration (not a closed-form Macaulay/modified
    duration formula) -- centred finite difference around the base curve, consistent
    with how the full-reprice engine itself discounts cashflows."""
    base = bond_price(face, coupon_rate, maturity_years, curve, credit_spread_bp)
    up = bond_price(face, coupon_rate, maturity_years, curve.shocked(parallel_bp=bump_bp), credit_spread_bp)
    down = bond_price(face, coupon_rate, maturity_years, curve.shocked(parallel_bp=-bump_bp), credit_spread_bp)
    d_price_d_rate = (up - down) / (2 * bump_bp / 10000.0)
    return -d_price_d_rate / base  # modified-duration convention


def bond_full_vs_duration_only(face: float, coupon_rate: float, maturity_years: float, curve: YieldCurve, shock_bps: list[float], credit_spread_bp: float = 0.0) -> list[ApproxComparison]:
    base_price = bond_price(face, coupon_rate, maturity_years, curve, credit_spread_bp)
    duration = effective_duration(face, coupon_rate, maturity_years, curve, credit_spread_bp)

    results = []
    for shock_bp in shock_bps:
        full = bond_price(face, coupon_rate, maturity_years, curve.shocked(parallel_bp=shock_bp), credit_spread_bp)
        naive = base_price * (1 - duration * (shock_bp / 10000.0))
        results.append(ApproxComparison(shock_label=f"{shock_bp:+.0f}bp", full_reprice_value=full, naive_approx_value=naive))
    return results


def option_full_vs_delta_only(spot: float, strike: float, maturity_years: float, risk_free_rate: float, volatility: float, option_type: str, spot_shocks_pct: list[float]) -> list[ApproxComparison]:
    base = black_scholes(spot, strike, maturity_years, risk_free_rate, volatility, option_type)

    results = []
    for shock_pct in spot_shocks_pct:
        shocked_spot = spot * (1 + shock_pct)
        full = black_scholes(shocked_spot, strike, maturity_years, risk_free_rate, volatility, option_type)
        naive = base.price + base.delta * (shocked_spot - spot)  # delta-only, ignores gamma
        results.append(ApproxComparison(shock_label=f"{shock_pct:+.0%} spot", full_reprice_value=full.price, naive_approx_value=naive))
    return results
