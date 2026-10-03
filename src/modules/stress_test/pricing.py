"""Pricing functions for bonds, interest-rate swaps, and equity options.
Full cashflow discounting / closed-form Black-Scholes -- no shortcuts -- so the
Phase 4.5 "full reprice vs naive duration/delta approximation" comparison is
measuring a real difference, not two versions of the same shortcut.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from scipy.stats import norm

from src.modules.stress_test.curve import YieldCurve


def bond_price(
    face: float,
    coupon_rate: float,
    maturity_years: float,
    curve: YieldCurve,
    credit_spread_bp: float = 0.0,
    freq: int = 2,
) -> float:
    """Full cashflow discounting: price = sum(coupon * DF(t)) + face * DF(T),
    DF taken off the risk-free curve plus a flat credit spread."""
    spread = credit_spread_bp / 10000.0
    n_periods = max(round(maturity_years * freq), 1)
    coupon_per_period = face * coupon_rate / freq
    price = 0.0
    for i in range(1, n_periods + 1):
        t = i / freq
        r = curve.zero_rate(t) + spread
        df = 1.0 / ((1.0 + r / freq) ** (freq * t))
        cf = coupon_per_period + (face if i == n_periods else 0.0)
        price += cf * df
    return price


@dataclass
class SwapLegResult:
    pv_fixed: float
    pv_floating: float
    value_payer_fixed: float  # value to the party paying fixed / receiving floating


def price_interest_rate_swap(
    notional: float,
    fixed_rate: float,
    maturity_years: float,
    curve: YieldCurve,
    freq: int = 2,
) -> SwapLegResult:
    """Standard simplification: the floating leg reprices to par at each reset,
    so PV(floating) = notional * (1 - DF(T)); PV(fixed) is priced like a bond's
    coupon stream without the final principal repayment netting out against the
    floating leg's own principal exchange (both legs' notional exchanges cancel
    in a standard swap, so neither is included). Stated in docs/ASSUMPTIONS.md."""
    n_periods = max(round(maturity_years * freq), 1)
    coupon_per_period = notional * fixed_rate / freq
    pv_fixed = 0.0
    for i in range(1, n_periods + 1):
        t = i / freq
        df = curve.discount_factor(t)
        pv_fixed += coupon_per_period * df
    df_T = curve.discount_factor(maturity_years)
    pv_floating = notional * (1.0 - df_T)
    value_payer_fixed = pv_floating - pv_fixed
    return SwapLegResult(pv_fixed=pv_fixed, pv_floating=pv_floating, value_payer_fixed=value_payer_fixed)


def swap_dv01(notional: float, fixed_rate: float, maturity_years: float, curve: YieldCurve, freq: int = 2) -> float:
    """DV01 = value change for a 1bp parallel rate decrease (the market
    convention: DV01 is quoted as a positive number for a receiver position).
    Computed by finite difference (bump-and-reprice), not a closed-form
    approximation -- this IS the "full reprice" leg of the required
    full-vs-naive comparison for swaps."""
    base = price_interest_rate_swap(notional, fixed_rate, maturity_years, curve, freq).value_payer_fixed
    bumped_curve = curve.shocked(parallel_bp=-1.0)
    bumped = price_interest_rate_swap(notional, fixed_rate, maturity_years, bumped_curve, freq).value_payer_fixed
    return bumped - base


@dataclass
class OptionResult:
    price: float
    delta: float
    gamma: float


def black_scholes(
    spot: float,
    strike: float,
    maturity_years: float,
    risk_free_rate: float,
    volatility: float,
    option_type: str = "put",
) -> OptionResult:
    """Standard Black-Scholes-Merton, no dividend yield (q=0)."""
    if maturity_years <= 0 or volatility <= 0:
        intrinsic = max(0.0, (strike - spot) if option_type == "put" else (spot - strike))
        return OptionResult(price=intrinsic, delta=0.0, gamma=0.0)

    d1 = (math.log(spot / strike) + (risk_free_rate + 0.5 * volatility**2) * maturity_years) / (
        volatility * math.sqrt(maturity_years)
    )
    d2 = d1 - volatility * math.sqrt(maturity_years)
    disc = math.exp(-risk_free_rate * maturity_years)

    if option_type == "call":
        price = spot * norm.cdf(d1) - strike * disc * norm.cdf(d2)
        delta = norm.cdf(d1)
    elif option_type == "put":
        price = strike * disc * norm.cdf(-d2) - spot * norm.cdf(-d1)
        delta = norm.cdf(d1) - 1.0
    else:
        raise ValueError(f"unknown option_type: {option_type}")

    gamma = norm.pdf(d1) / (spot * volatility * math.sqrt(maturity_years))
    return OptionResult(price=price, delta=delta, gamma=gamma)


def fx_forward_value(notional: float, fx_pct_move: float) -> float:
    """Simplification, stated plainly: linear P&L = notional x FX % move. A full
    forward-points / covered-interest-parity reprice is out of scope for this
    prototype (FX is a secondary shock channel here, not the primary one) --
    see docs/ASSUMPTIONS.md."""
    return notional * fx_pct_move


def expected_loss(ead: float, pd: float, lgd: float) -> float:
    """EL = PD x LGD x EAD -- the standard credit-risk expected-loss identity."""
    return ead * pd * lgd
