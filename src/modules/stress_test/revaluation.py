"""Full-reprice portfolio revaluation: values every position before and after a
shock, with P&L breakdown by asset class/sector/position, and the required
accounting split (see docs/ASSUMPTIONS.md "EL horizon and MTM/credit-loss
split"):

  (a) Mark-to-market P&L for bonds, swaps, options, FX forwards -- these are
      fair-valued (full cashflow discounting / closed-form pricing, see
      pricing.py), and a credit-spread-widening shock already shows up here as
      a price decline. This is the standard trading/AFS-book treatment.
  (b) Credit loss on loans = delta-EL (PD x LGD x EAD, PD bumped by the
      shock's pd_multiplier) -- loans are held at amortized cost (carrying
      value = notional - EL, i.e. provisioned), the standard banking-book
      treatment. Loans are NEVER also fair-valued/repriced off the curve or a
      credit spread -- there is exactly one channel for a loan's stress
      impact (its PD moving), not two. This is enforced by construction: loan
      "value" IS notional-minus-EL, so a loan's price/credit impact can't be
      counted twice by accident.

Total stressed loss = mtm_pnl (a) + credit_loss (b). Both are reported
separately AND summed, never silently merged into a single undifferentiated
number."""
from __future__ import annotations

from dataclasses import dataclass

from src.modules.stress_test.curve import YieldCurve
from src.modules.stress_test.pricing import black_scholes, bond_price, expected_loss, fx_forward_value, price_interest_rate_swap
from src.modules.stress_test.portfolio import Position
from src.modules.stress_test.shocks import RATING_BASE_SPREAD_BP, ShockSet

MTM_ASSET_CLASSES = {"bond", "swap", "option", "fx_forward"}
CREDIT_ASSET_CLASSES = {"loan"}


@dataclass
class PositionValuation:
    position: Position
    value: float            # fair value for MTM asset classes; carrying value (notional - EL) for loans
    expected_loss: float     # PD x LGD x EAD; the only channel through which a loan's stress impact flows


def value_position(pos: Position, curve: YieldCurve, equity_spot: dict[str, float]) -> PositionValuation:
    el = expected_loss(ead=pos.notional, pd=pos.pd, lgd=pos.lgd)

    if pos.asset_class == "loan":
        # Amortized-cost / provisioning treatment: carrying value = notional - EL.
        # No curve/spread repricing for loans -- see module docstring.
        value = pos.notional - el
        return PositionValuation(position=pos, value=value, expected_loss=el)

    base_spread_bp = RATING_BASE_SPREAD_BP.get(pos.rating, RATING_BASE_SPREAD_BP["BBB"])

    if pos.asset_class == "bond":
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
        quantity = pos.notional / spot
        result = black_scholes(
            spot=spot, strike=strike, maturity_years=pos.maturity_years,
            risk_free_rate=curve.zero_rate(pos.maturity_years), volatility=pos.extra["volatility"],
            option_type=pos.extra["option_type"],
        )
        value = quantity * result.price
    elif pos.asset_class == "fx_forward":
        value = fx_forward_value(notional=pos.notional, fx_pct_move=0.0)
    else:
        raise ValueError(f"unknown asset_class: {pos.asset_class}")

    return PositionValuation(position=pos, value=value, expected_loss=el)


def value_position_shocked(pos: Position, curve: YieldCurve, equity_spot: dict[str, float], shock: ShockSet) -> PositionValuation:
    """Same as value_position but under a shocked curve/spot/vol/PD, scoped by
    shock.applies_to() (portfolio-wide shocks hit everything; entity-specific
    shocks only hit the named ticker/sector/country)."""
    in_scope = shock.applies_to(pos.sector, pos.country, {pos.extra.get("underlying")} if pos.asset_class == "option" else None)

    if not in_scope:
        return value_position(pos, curve, equity_spot)

    shocked_pd = min(pos.pd * shock.pd_multiplier, 1.0)
    el = expected_loss(ead=pos.notional, pd=shocked_pd, lgd=pos.lgd)

    if pos.asset_class == "loan":
        value = pos.notional - el  # the ONLY channel: higher stressed PD -> higher EL -> lower carrying value
        return PositionValuation(position=pos, value=value, expected_loss=el)

    shocked_curve = curve.shocked(parallel_bp=shock.rate_parallel_bp)
    shocked_spot = {k: v * (1 + shock.equity_pct_move) for k, v in equity_spot.items()}
    base_spread_bp = RATING_BASE_SPREAD_BP.get(pos.rating, RATING_BASE_SPREAD_BP["BBB"])
    spread_bump = shock.credit_spread_bump_bp(pos.rating)

    if pos.asset_class == "bond":
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
        strike = pos.extra["moneyness"] * base_spot
        quantity = pos.notional / base_spot
        shocked_vol = pos.extra["volatility"] * shock.vol_multiplier
        result = black_scholes(
            spot=shocked_underlying_spot, strike=strike, maturity_years=pos.maturity_years,
            risk_free_rate=shocked_curve.zero_rate(pos.maturity_years), volatility=shocked_vol,
            option_type=pos.extra["option_type"],
        )
        value = quantity * result.price
    elif pos.asset_class == "fx_forward":
        fx_pct_move = shock.equity_pct_move * 0.3
        value = fx_forward_value(notional=pos.notional, fx_pct_move=fx_pct_move)
    else:
        raise ValueError(f"unknown asset_class: {pos.asset_class}")

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
        """Combined P&L across ALL positions (MTM instruments + loans' carrying
        value). Equals mtm_pnl + credit_loss by construction (see module
        docstring) -- reported for convenience, but mtm_pnl/credit_loss below
        are the numbers that should actually be shown as two separate lines."""
        return self.total_value_after - self.total_value_before

    @property
    def mtm_pnl(self) -> float:
        """(a) Mark-to-market P&L: bonds, swaps, options, FX forwards only."""
        return sum(
            a.value - b.value for b, a in zip(self.before, self.after)
            if b.position.asset_class in MTM_ASSET_CLASSES
        )

    @property
    def credit_loss(self) -> float:
        """(b) Credit loss on loans = delta-EL, expressed as a loss (positive
        number = a loss) i.e. EL_after - EL_before. Equals -(loan value
        change) by construction."""
        return sum(
            a.expected_loss - b.expected_loss for b, a in zip(self.before, self.after)
            if b.position.asset_class in CREDIT_ASSET_CLASSES
        )

    @property
    def total_stressed_loss(self) -> float:
        """(a) + (b): mtm_pnl is already signed as a P&L (negative = loss),
        credit_loss is signed as a loss (positive = loss), so this is
        mtm_pnl - credit_loss to express both on a common "P&L" sign
        convention (positive = gain)."""
        return self.mtm_pnl - self.credit_loss

    @property
    def total_el_before(self) -> float:
        """ALL positions' EL (loans + bonds, which also carry PD/LGD in the
        portfolio generator) -- informational only. Only the LOAN portion
        (see credit_loss above) is summed into total_stressed_loss; bond EL is
        not double-counted on top of its own credit-spread-driven MTM move."""
        return sum(v.expected_loss for v in self.before)

    @property
    def total_el_after(self) -> float:
        return sum(v.expected_loss for v in self.after)

    def pnl_by_asset_class(self) -> dict[str, float]:
        """For loans this is the carrying-value change (= -delta-EL, i.e. the
        credit loss shown as a P&L-sign number), for everything else it's the
        MTM value change -- both drawn from the same `value` field, so this
        sums exactly to total_pnl with no special-casing needed."""
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
