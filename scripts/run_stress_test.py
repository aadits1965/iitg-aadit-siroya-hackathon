#!/usr/bin/env python
"""Phase 4 end-to-end: load the real synthetic portfolio + real cached market
data, evaluate real signals through the trigger engine, and revalue the
portfolio for every fired decision. Writes results/stress_test_output.json.

Hard gate: refuses to run against a SYNTHETIC_TEST_ONLY curve -- that curve
must never produce output presented as a real stress-test result (see
src/modules/stress_test/curve.py and docs/ASSUMPTIONS.md).
"""
import csv
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.modules.stress_test.curve import load_curve  # noqa: E402
from src.modules.stress_test.naive_approx import bond_full_vs_duration_only, option_full_vs_delta_only  # noqa: E402
from src.modules.stress_test.portfolio import load_portfolio  # noqa: E402
from src.modules.stress_test.revaluation import revalue_portfolio  # noqa: E402
from src.modules.stress_test.shocks import build_shock_set  # noqa: E402
from src.modules.stress_test.trigger import evaluate_signals, load_signals_from_file  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[1]
PORTFOLIO_PATH = ROOT / "data" / "synthetic" / "portfolio.csv"
EQUITY_CACHE_PATH = ROOT / "data" / "cache" / "market" / "equity_prices.csv"
OUT_PATH = ROOT / "results" / "stress_test_output.json"


def load_latest_equity_spot() -> dict[str, float]:
    spot: dict[str, tuple[str, float]] = {}
    with EQUITY_CACHE_PATH.open("r", encoding="utf-8") as f:
        for row in csv.DictReader(line for line in f if not line.startswith("#")):
            ticker, d, px = row["ticker"], row["date"], float(row["close"])
            if ticker not in spot or d > spot[ticker][0]:
                spot[ticker] = (d, px)
    return {t: px for t, (d, px) in spot.items()}


def summarize(result, label: str) -> dict:
    return {
        "label": label,
        "event_class": result.shock.event_class,
        "tier": result.shock.tier_name,
        "scope": result.shock.scope,
        "total_value_before": round(result.total_value_before, 2),
        "total_value_after": round(result.total_value_after, 2),
        "total_pnl": round(result.total_pnl, 2),
        "total_pnl_pct": round(result.total_pnl / result.total_value_before * 100, 4) if result.total_value_before else None,
        "total_el_before": round(result.total_el_before, 2),
        "total_el_after": round(result.total_el_after, 2),
        "pnl_by_asset_class": {k: round(v, 2) for k, v in result.pnl_by_asset_class().items()},
        "pnl_by_sector": {k: round(v, 2) for k, v in result.pnl_by_sector().items()},
        "top_10_contributors": [{"position_id": pid, "pnl": round(pnl, 2)} for pid, pnl in result.top_contributors(10)],
    }


def main():
    curve = load_curve()  # raises MissingCurveCacheError if no real cache -- no silent fallback
    if curve.is_synthetic_test_only:
        raise RuntimeError("refusing to run: curve is SYNTHETIC_TEST_ONLY, must never appear in real output")
    logger.info("curve as_of=%s source=%s", curve.as_of, curve.source)

    portfolio = load_portfolio(PORTFOLIO_PATH)
    equity_spot = load_latest_equity_spot()
    logger.info("loaded %d positions, %d equity spot prices", len(portfolio), len(equity_spot))

    signals = load_signals_from_file()
    logger.info("loaded %d real signals from results/signals.jsonl", len(signals))
    decisions = evaluate_signals(signals)
    fired = [d for d in decisions if d.fired]
    logger.info("%d / %d signals fired a stress test (impact > threshold, cooldown clear)", len(fired), len(decisions))

    output = {
        "curve_as_of": curve.as_of.isoformat(),
        "curve_source": curve.source,
        "n_signals_evaluated": len(decisions),
        "n_fired": len(fired),
        "fired_scenarios": [],
    }

    # Cap to the 5 highest-impact fired decisions for a readable output file.
    for d in sorted(fired, key=lambda x: -x.impact_score)[:5]:
        shock = build_shock_set(d.event_class, tickers=d.tickers, sectors=d.sectors, countries=d.countries)
        result = revalue_portfolio(portfolio, curve, equity_spot, shock)
        output["fired_scenarios"].append({
            "signal_id": d.signal_id,
            "impact_score": d.impact_score,
            "trigger_reason": d.reason,
            **summarize(result, label=f"{d.event_class} (impact={d.impact_score})"),
        })

    # Always include one illustrative scenario run even if nothing fired yet in the
    # cached signals, so Module B's dashboard has something to show.
    example_shock = build_shock_set("Macroeconomic")
    example_result = revalue_portfolio(portfolio, curve, equity_spot, example_shock)
    output["example_severe_macro_scenario"] = summarize(example_result, label="Illustrative: Fed severely-adverse macro shock, portfolio-wide")

    # Required Phase 4.5 comparison: full reprice vs naive approximation, on a
    # representative bond and option actually in the portfolio.
    sample_bond = next(p for p in portfolio if p.asset_class == "bond" and not p.extra.get("is_sovereign"))
    bond_comparison = bond_full_vs_duration_only(
        face=sample_bond.notional, coupon_rate=sample_bond.extra["coupon_rate"],
        maturity_years=sample_bond.maturity_years, curve=curve,
        credit_spread_bp=sample_bond.extra.get("credit_spread_bp", 0),
        shock_bps=[10, 50, 100, 200, -200],
    )
    sample_option = next((p for p in portfolio if p.asset_class == "option"), None)
    option_comparison = []
    if sample_option:
        spot = equity_spot[sample_option.extra["underlying"]]
        option_comparison = option_full_vs_delta_only(
            spot=spot, strike=sample_option.extra["moneyness"] * spot, maturity_years=sample_option.maturity_years,
            risk_free_rate=curve.zero_rate(sample_option.maturity_years), volatility=sample_option.extra["volatility"],
            option_type=sample_option.extra["option_type"], spot_shocks_pct=[-0.05, -0.20, -0.40, 0.05, 0.20],
        )

    output["naive_vs_full_reprice"] = {
        "bond": {
            "position_id": sample_bond.position_id,
            "comparisons": [
                {"shock": c.shock_label, "full_reprice": round(c.full_reprice_value, 4),
                 "naive_duration_only": round(c.naive_approx_value, 4), "error": round(c.error, 4)}
                for c in bond_comparison
            ],
        },
        "option": {
            "position_id": sample_option.position_id if sample_option else None,
            "comparisons": [
                {"shock": c.shock_label, "full_reprice": round(c.full_reprice_value, 4),
                 "naive_delta_only": round(c.naive_approx_value, 4), "error": round(c.error, 4)}
                for c in option_comparison
            ],
        },
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(output, indent=2), encoding="utf-8")

    print(f"\n=== Stress test summary ===")
    print(f"Curve as-of: {curve.as_of} ({curve.source[:80]}...)")
    print(f"Portfolio: {len(portfolio)} positions, total notional ${sum(p.notional for p in portfolio):,.0f}")
    print(f"Signals: {len(decisions)} evaluated, {len(fired)} fired")
    print(f"\nIllustrative severe macro scenario:")
    print(f"  Value before: ${example_result.total_value_before:,.0f}")
    print(f"  Value after:  ${example_result.total_value_after:,.0f}")
    print(f"  P&L:          ${example_result.total_pnl:,.0f} ({example_result.total_pnl/example_result.total_value_before*100:.2f}%)")
    print(f"  EL before -> after: ${example_result.total_el_before:,.0f} -> ${example_result.total_el_after:,.0f}")
    print(f"\nWritten to {OUT_PATH}")


if __name__ == "__main__":
    main()
