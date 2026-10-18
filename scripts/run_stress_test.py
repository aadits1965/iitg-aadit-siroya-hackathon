#!/usr/bin/env python
"""Phase 4 end-to-end: load the real synthetic portfolio + real cached market
data, evaluate real signals through the trigger engine, and revalue the
portfolio for every fired decision. Writes results/stress_test_output.json.

Hard gates:
  - refuses to run against a SYNTHETIC_TEST_ONLY curve (must never appear in
    real output -- see src/modules/stress_test/curve.py)
  - if the market data is PROVISIONAL (WebFetch-sourced, not a direct
    download -- see docs/DATA_VERIFICATION.md section 9), the output is
    tagged `"data_provisional": true` at the top level and printed with a loud
    warning. Nothing with that flag set should go into the deck/README until
    `scripts/verify_provisional_data.py` passes.

The "headline" scenario reported is the REAL highest-impact fired signal (not
a manually chosen illustrative example) -- see the review feedback this fixes:
an earlier run's console summary printed a manually-constructed "illustrative"
scenario right where a reader would expect the real result, which was
genuinely ambiguous. That illustrative scenario is still included, but clearly
labelled and kept separate.
"""
import json
import logging
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.dashboard.data import PORTFOLIO_PATH, is_equity_data_provisional, load_latest_equity_spot  # noqa: E402
from src.modules.stress_test.curve import load_curve  # noqa: E402
from src.modules.stress_test.naive_approx import bond_full_vs_duration_only, option_full_vs_delta_only  # noqa: E402
from src.modules.stress_test.portfolio import load_portfolio  # noqa: E402
from src.modules.stress_test.revaluation import revalue_portfolio  # noqa: E402
from src.modules.stress_test.shocks import build_shock_set  # noqa: E402
from src.modules.stress_test.trigger import evaluate_signals, load_signals_from_file  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[1]
OUT_PATH = ROOT / "results" / "stress_test_output.json"


def summarize(result, label: str, extra: dict | None = None) -> dict:
    out = {
        "label": label,
        "event_class": result.shock.event_class,
        "tier": result.shock.tier_name,
        "narrative": result.shock.narrative,
        "scope": result.shock.scope,
        "total_value_before": round(result.total_value_before, 2),
        "total_value_after": round(result.total_value_after, 2),
        "mtm_pnl": round(result.mtm_pnl, 2),
        "credit_loss_on_loans": round(result.credit_loss, 2),
        "total_stressed_loss": round(result.total_stressed_loss, 2),
        "total_stressed_loss_pct": round(result.total_stressed_loss / result.total_value_before * 100, 4) if result.total_value_before else None,
        "total_el_before_all_positions_memo_only": round(result.total_el_before, 2),
        "total_el_after_all_positions_memo_only": round(result.total_el_after, 2),
        "pnl_by_asset_class": {k: round(v, 2) for k, v in result.pnl_by_asset_class().items()},
        "pnl_by_sector": {k: round(v, 2) for k, v in result.pnl_by_sector().items()},
        "top_10_contributors": [{"position_id": pid, "pnl": round(pnl, 2)} for pid, pnl in result.top_contributors(10)],
    }
    if extra:
        out.update(extra)
    return out


def main():
    curve = load_curve()  # raises MissingCurveCacheError if no real cache -- no silent fallback
    if curve.is_synthetic_test_only:
        raise RuntimeError("refusing to run: curve is SYNTHETIC_TEST_ONLY, must never appear in real output")

    data_provisional = curve.is_provisional or is_equity_data_provisional()
    logger.info("curve as_of=%s is_provisional=%s source=%s", curve.as_of, curve.is_provisional, curve.source[:100])
    if data_provisional:
        logger.warning("MARKET DATA IS PROVISIONAL (WebFetch-sourced, not a direct download). "
                        "Run scripts/verify_provisional_data.py before using this output in the deck/README.")

    portfolio = load_portfolio(PORTFOLIO_PATH)
    equity_spot = load_latest_equity_spot()
    logger.info("loaded %d positions, %d equity spot prices", len(portfolio), len(equity_spot))

    signals = load_signals_from_file()
    signals_by_id = {s["signal_id"]: s for s in signals}
    logger.info("loaded %d real signals from results/signals.jsonl", len(signals))
    decisions = evaluate_signals(signals)
    fired = [d for d in decisions if d.fired]
    logger.info("%d / %d signals fired a stress test (impact > threshold, sentiment < 0, cooldown clear)", len(fired), len(decisions))

    output = {
        "data_provisional": data_provisional,
        "data_provisional_warning": (
            "Curve and/or equity prices were fetched via Claude's WebFetch tool (summarising model in the "
            "loop), not a direct download. Do NOT use this output in the deck/README until "
            "scripts/verify_provisional_data.py passes. See docs/DATA_VERIFICATION.md section 9."
        ) if data_provisional else None,
        "curve_as_of": curve.as_of.isoformat(),
        "curve_source": curve.source,
        "n_signals_evaluated": len(decisions),
        "n_fired": len(fired),
        "fired_scenarios": [],
    }

    fired_sorted = sorted(fired, key=lambda x: -x.impact_score)

    # Cap to the 5 highest-impact fired decisions for a readable output file.
    fired_results = []
    for d in fired_sorted[:5]:
        shock = build_shock_set(d.event_class, tickers=d.tickers, sectors=d.sectors, countries=d.countries)
        result = revalue_portfolio(portfolio, curve, equity_spot, shock)
        src_signal = signals_by_id.get(d.signal_id, {})
        entry = summarize(
            result, label=f"REAL triggered signal: {d.event_class} (impact={d.impact_score})",
            extra={
                "signal_id": d.signal_id,
                "impact_score": d.impact_score,
                "trigger_reason": d.reason,
                "headline_text": src_signal.get("text_preview"),
                "sources": src_signal.get("sources"),
                "sentiment": src_signal.get("sentiment"),
                "impact_components": src_signal.get("impact", {}).get("components"),
            },
        )
        output["fired_scenarios"].append(entry)
        fired_results.append((d, result, entry))

    # The REAL headline: the single highest-impact fired signal, not a manually
    # chosen scenario. None of these exist if nothing fired -- handled below.
    headline = fired_results[0] if fired_results else None
    if headline:
        output["headline_scenario"] = headline[2]
        output["headline_scenario"]["note"] = (
            "This IS the highest-impact real triggered signal from results/signals.jsonl, not a manually "
            "chosen illustrative scenario."
        )

    # Illustrative example, kept SEPARATE and clearly labelled -- never presented as the headline result.
    example_shock = build_shock_set("Macroeconomic")
    example_result = revalue_portfolio(portfolio, curve, equity_spot, example_shock)
    output["illustrative_example_NOT_from_a_real_trigger"] = summarize(
        example_result,
        label="Manual scenario — not triggered by a real signal",
    )

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

    print("\n=== Stress test summary ===")
    if data_provisional:
        print("*** WARNING: market data is PROVISIONAL -- do not use these numbers in the deck/README. ***")
        print("*** Run scripts/verify_provisional_data.py first.                                        ***")
    print(f"Curve as-of: {curve.as_of} ({curve.source[:80]}...)")
    print(f"Portfolio: {len(portfolio)} positions, total notional ${sum(p.notional for p in portfolio):,.0f}")
    print(f"Signals: {len(decisions)} evaluated, {len(fired)} fired\n")

    if headline:
        d, result, entry = headline
        print("=== HEADLINE (real triggered signal, highest impact) ===")
        print(f"Signal: {d.signal_id} | impact={d.impact_score} | event_class={d.event_class}")
        print(f"Headline text: {entry['headline_text']}")
        print(f"Scenario: {result.shock.tier_name} ({result.shock.scope}) -- {result.shock.narrative}")
        print(f"  Value before: ${result.total_value_before:,.0f}")
        print(f"  Value after:  ${result.total_value_after:,.0f}")
        print(f"  MTM P&L (bonds/swaps/options/FX):  ${result.mtm_pnl:,.0f}")
        print(f"  Credit loss (loans, delta-EL):      ${result.credit_loss:,.0f}")
        print(f"  Total stressed loss:                ${result.total_stressed_loss:,.0f} "
              f"({result.total_stressed_loss/result.total_value_before*100:.2f}%)")
        print(f"  P&L by asset class: {entry['pnl_by_asset_class']}")
    else:
        print("No signal fired a stress test in this run.")

    print("\n=== Illustrative example (NOT a real trigger) ===")
    print(f"  Total stressed loss: ${example_result.total_stressed_loss:,.0f} "
          f"({example_result.total_stressed_loss/example_result.total_value_before*100:.2f}%)")

    print(f"\nAll {len(fired_results)} fired scenarios + full naive-vs-full-reprice tables written to {OUT_PATH}")


if __name__ == "__main__":
    main()
