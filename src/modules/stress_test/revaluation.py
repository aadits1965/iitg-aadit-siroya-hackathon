"""Full-reprice portfolio revaluation: values every position before and after a
shock, with P&L breakdown by asset class/sector/position, credit EL before/after,
and top contributors. See pricing.py for the actual pricing functions used --
no shortcuts (full cashflow discounting for bonds/loans, finite-difference DV01
for swaps, closed-form Black-Scholes for options)."""
from __future__ import annotations

from dataclasses import dataclass, field

from src.modules.stress_test.curve import YieldCurve
from src.modules.stress_test.pricing import black_scholes, bond_price, expected_loss, fx_forward_value, price_interest_rate_swap
from src.modules.stress_test.portfolio import Position
from src.modules.stress_test.shocks import RATING_BASE_SPREAD_BP, ShockSet


@dataclass
class PositionValuation:
    position: Position
    value: float
    expected_loss: float


def value_position(pos: Position, curve: YieldCurve, equity_spot: dict[str, float]) -> PositionValuation:
    base_spread_bp = RATING_BASE_SPREAD_BP.get(pos.rating, RATING_BASE_SPREAD_BP["BBB"])

    if pos.asset_class == "loan":
        value = bond_price(
            face=pos.notional, coupon_rate=pos.extra["interest_rate"], maturity_years=pos.maturity_years,
            curve=curve, credit_spread_bp=base_spread_bp,
        )
    elif pos.asset_class == "bond":
        spread = 0.0 if pos.extra.get("is_sovereign") else base_spread_bp + pos.extra.get("credit_spread_bp", 0.0)
        value = bond_price(
            face=pos.notional, coupon_rate=pos.extra["coupon_rate"], maturity_years=pos.maturity_years,
            curve=curve, credit_spread_bp=spread,
        )
    elif pos.asset_class == "swap":
        result = price_interest_rate_swap(
            notional=pos.notional, fixed_rate=pos.extra["fixed_rate"], maturity_years=pos.maturity_years, curve=curve,
        )
        value = result.value_payer_fixed if pos.extra["direction"] == "payer" else -result.value_payer_fixed
    elif pos.asset_class == "option":
        underlying = pos.extra["underlying"]
        spot = equity_spot.get(underlying)
        if spot is None:
            raise KeyError(f"no spot price available for option underlying {underlying!r}")
        strike = pos.extra["moneyness"] * spot
        quantity = pos.notional / spot  # notional expressed as an equivalent share count at current spot
        result = black_scholes(
            spot=spot, strike=strike, maturity_years=pos.maturity_years,
            risk_free_rate=curve.zero_rate(pos.maturity_years), volatility=pos.extra["volatility"],
            option_type=pos.extra["option_type"],
        )
        value = quantity * result.price
    elif pos.asset_class == "fx_forward":
        value = fx_forward_value(notional=pos.notional, fx_pct_move=0.0)  # unshocked baseline = 0 P&L
    else:
        raise ValueError(f"unknown asset_class: {pos.asset_class}")

    el = expected_loss(ead=pos.notional, pd=pos.pd, lgd=pos.lgd)
    return PositionValuation(position=pos, value=value, expected_loss=el)


def value_position_shocked(pos: Position, curve: YieldCurve, equity_spot: dict[str, float], shock: ShockSet) -> PositionValuation:
    """Same as value_position but under a shocked curve/spot/vol/PD, scoped by
    shock.applies_to() (portfolio-wide shocks hit everything; entity-specific
    shocks only hit the named ticker/sector/country)."""
    in_scope = shock.applies_to(pos.sector, pos.country, {pos.extra.get("underlying")} if pos.asset_class == "option" else None)

    if not in_scope:
        return value_position(pos, curve, equity_spot)

    shocked_curve = curve.shocked(parallel_bp=shock.rate_parallel_bp)
    shocked_spot = {k: v * (1 + shock.equity_pct_move) for k, v in equity_spot.items()}
    base_spread_bp = RATING_BASE_SPREAD_BP.get(pos.rating, RATING_BASE_SPREAD_BP["BBB"])
    spread_bump = shock.credit_spread_bump_bp(pos.rating)

    if pos.asset_class == "loan":
        value = bond_price(
            face=pos.notional, coupon_rate=pos.extra["interest_rate"], maturity_years=pos.maturity_years,
            curve=shocked_curve, credit_spread_bp=base_spread_bp + spread_bump,
        )
    elif pos.asset_class == "bond":
        spread = (0.0 if pos.extra.get("is_sovereign") else base_spread_bp + pos.extra.get("credit_spread_bp", 0.0)) + spread_bump
        value = bond_price(
            face=pos.notional, coupon_rate=pos.extra["coupon_rate"], maturity_years=pos.maturity_years,
            curve=shocked_curve, credit_spread_bp=spread,
        )
    elif pos.asset_class == "swap":
        result = price_interest_rate_swap(
            notional=pos.notional, fixed_rate=pos.extra["fixed_rate"], maturity_years=pos.maturity_years, curve=shocked_curve,
        )
        value = result.value_payer_fixed if pos.extra["direction"] == "payer" else -result.value_payer_fixed
    elif pos.asset_class == "option":
        underlying = pos.extra["underlying"]
        base_spot = equity_spot.get(underlying)
        if base_spot is None:
            raise KeyError(f"no spot price available for option underlying {underlying!r}")
        shocked_underlying_spot = base_spot * (1 + shock.equity_pct_move)
        strike = pos.extra["moneyness"] * base_spot  # strike fixed at trade inception, not re-struck
        quantity = pos.notional / base_spot
        shocked_vol = pos.extra["volatility"] * shock.vol_multiplier
        result = black_scholes(
            spot=shocked_underlying_spot, strike=strike, maturity_years=pos.maturity_years,
            risk_free_rate=shocked_curve.zero_rate(pos.maturity_years), volatility=shocked_vol,
            option_type=pos.extra["option_type"],
        )
        value = quantity * result.price
    elif pos.asset_class == "fx_forward":
        # FX pct move proxied by the equity shock magnitude scaled down (illustrative;
        # this project's shock library doesn't define a separate FX shock -- see
        # docs/ASSUMPTIONS.md). Direction: risk-off equity selloffs often come with
        # USD strength, modelled here as a move against the non-USD leg.
        fx_pct_move = shock.equity_pct_move * 0.3
        value = fx_forward_value(notional=pos.notional, fx_pct_move=fx_pct_move)
    else:
        raise ValueError(f"unknown asset_class: {pos.asset_class}")

    shocked_pd = min(pos.pd * shock.pd_multiplier, 1.0)
    el = expected_loss(ead=pos.notional, pd=shocked_pd, lgd=pos.lgd)
    return PositionValuation(position=pos, value=value, expected_loss=el)


@dataclass
class RevaluationResult:
    before: list[PositionValuation]
    after: list[PositionValuation]
    shock: ShockSet

    @property
    def total_value_before(self) -> float:
        return sum(v.value for v in self.before)

    @property
    def total_value_after(self) -> float:
        return sum(v.value for v in self.after)

    @property
    def total_pnl(self) -> float:
        return self.total_value_after - self.total_value_before

    @property
    def total_el_before(self) -> float:
        return sum(v.expected_loss for v in self.before)

    @property
    def total_el_after(self) -> float:
        return sum(v.expected_loss for v in self.after)

    def pnl_by_asset_class(self) -> dict[str, float]:
        out: dict[str, float] = {}
        for b, a in zip(self.before, self.after):
            out.setdefault(b.position.asset_class, 0.0)
            out[b.position.asset_class] += a.value - b.value
        return out

    def pnl_by_sector(self) -> dict[str, float]:
        out: dict[str, float] = {}
        for b, a in zip(self.before, self.after):
            out.setdefault(b.position.sector, 0.0)
            out[b.position.sector] += a.value - b.value
        return out

    def top_contributors(self, n: int = 10) -> list[tuple[str, float]]:
        pnls = [(b.position.position_id, a.value - b.value) for b, a in zip(self.before, self.after)]
        pnls.sort(key=lambda x: x[1])
        return pnls[:n]


def revalue_portfolio(positions: list[Position], curve: YieldCurve, equity_spot: dict[str, float], shock: ShockSet) -> RevaluationResult:
    before = [value_position(p, curve, equity_spot) for p in positions]
    after = [value_position_shocked(p, curve, equity_spot, shock) for p in positions]
    return RevaluationResult(before=before, after=after, shock=shock)
