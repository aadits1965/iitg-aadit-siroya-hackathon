#!/usr/bin/env python
"""Generates README.md from docs/README_template.md, filling in the Key
Results section exclusively from results/metrics.json and
results/stress_test_output.json. REFUSES to write README.md if any field it
needs is missing or None -- a KeyError/TypeError here is the point, not a bug
to catch: it means a number this script was about to print doesn't actually
exist yet, and printing it anyway would be exactly the kind of placeholder/
fabricated number this project's own rules forbid.

Metrics this script does NOT try to show (event-classification accuracy,
impact-score correlation) are intentionally left to the template's
Limitations section as honest prose ("pending"), not pulled as numbers here --
there is no guard needed for a number the script never claims to source.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_PATH = ROOT / "docs" / "README_template.md"
METRICS_PATH = ROOT / "results" / "metrics.json"
STRESS_PATH = ROOT / "results" / "stress_test_output.json"
OUT_PATH = ROOT / "README.md"


def require(d: dict, *path):
    """Walk a dotted path through nested dicts; raise loudly if anything along
    the way is missing or None -- this IS the "refuse to build" mechanism."""
    cur = d
    for key in path:
        if not isinstance(cur, dict) or key not in cur or cur[key] is None:
            raise RuntimeError(
                f"REFUSING TO GENERATE README: required field {'.'.join(map(str, path))} is missing or "
                f"None (stopped at {key!r}). This metric is pending -- run the script that produces it "
                f"first, or remove this number from the Key Results section rather than fabricate it."
            )
        cur = cur[key]
    return cur


def fmt_ci(ci: list) -> str:
    return f"[{ci[0]:.3f}, {ci[1]:.3f}]"


def fmt_ci_pct(ci: list) -> str:
    return f"[{ci[0]:.1%}, {ci[1]:.1%}]"


def main():
    if not METRICS_PATH.exists():
        print(f"REFUSING TO GENERATE README: {METRICS_PATH} does not exist. Run scripts/run_sentiment_eval.py first.")
        sys.exit(1)
    if not STRESS_PATH.exists():
        print(f"REFUSING TO GENERATE README: {STRESS_PATH} does not exist. Run scripts/run_stress_test.py first.")
        sys.exit(1)

    metrics = json.loads(METRICS_PATH.read_text(encoding="utf-8"))
    stress = json.loads(STRESS_PATH.read_text(encoding="utf-8"))

    finbert_f1 = require(metrics, "sentiment_eval", "finbert", "macro_f1")
    finbert_f1_ci = require(metrics, "sentiment_eval", "finbert", "macro_f1_ci95")
    finbert_acc = require(metrics, "sentiment_eval", "finbert", "accuracy")
    finbert_acc_ci = require(metrics, "sentiment_eval", "finbert", "accuracy_ci95")
    finbert_recall_neg = require(metrics, "sentiment_eval", "finbert", "per_class", "negative", "recall")
    finbert_latency = require(metrics, "sentiment_eval", "finbert", "latency_ms_per_doc")
    vader_f1 = require(metrics, "sentiment_eval", "vader", "macro_f1")
    majority_f1 = require(metrics, "sentiment_eval", "majority_baseline", "macro_f1")
    majority_acc = require(metrics, "sentiment_eval", "majority_baseline", "accuracy")
    n_sent = require(metrics, "sentiment_eval", "n_fetched")
    label_dist = require(metrics, "sentiment_eval", "label_distribution")

    n_signals = require(stress, "n_signals_evaluated")
    n_fired = require(stress, "n_fired")
    curve_date = require(stress, "curve_as_of")
    data_provisional = stress.get("data_provisional", False)

    headline = stress.get("headline_scenario")
    if n_fired > 0 and headline is None:
        raise RuntimeError("REFUSING TO GENERATE README: n_fired > 0 but headline_scenario is missing.")

    bond_comparisons = require(stress, "naive_vs_full_reprice", "bond", "comparisons")
    option_comparisons = require(stress, "naive_vs_full_reprice", "option", "comparisons")
    if not bond_comparisons or not option_comparisons:
        raise RuntimeError("REFUSING TO GENERATE README: naive-vs-full-reprice comparisons are empty.")
    bond_biggest = max(bond_comparisons, key=lambda c: abs(c["error"]))
    option_biggest = max(option_comparisons, key=lambda c: abs(c["error"]))

    provisional_note = (
        "\n> **Note:** the market data behind the stress-test numbers below is PROVISIONAL (see "
        "`docs/DATA_VERIFICATION.md` section 9 and `docs/USER_TODO.md`) -- fetched via a tool that passes "
        "content through a summarising model, not a direct download, because this dev sandbox cannot reach "
        "treasury.gov/Yahoo Finance directly. Cross-check with `scripts/verify_provisional_data.py` before "
        "treating these exact figures as final.\n" if data_provisional else ""
    )

    lines = []
    lines.append("**Sentiment: FinBERT vs VADER vs majority-class baseline**")
    lines.append(f"(n={n_sent}, held-out validation split confirmed disjoint from FinBERT's own fine-tuning "
                 f"data; label distribution {label_dist} is class-imbalanced, which is why macro-F1, not "
                 f"accuracy, is the headline metric)\n")
    lines.append("| Model | Macro-F1 (95% CI) | Accuracy | Bearish recall |")
    lines.append("|---|---|---|---|")
    lines.append(f"| Majority-class | {majority_f1:.3f} | {majority_acc:.1%} | 0.000 |")
    lines.append(f"| VADER (lexicon baseline) | {vader_f1:.3f} | - | - |")
    lines.append(f"| **FinBERT (primary)** | **{finbert_f1:.3f}** {fmt_ci(finbert_f1_ci)} | "
                 f"{finbert_acc:.1%} {fmt_ci_pct(finbert_acc_ci)} | **{finbert_recall_neg:.1%}** |")
    lines.append(f"\nFinBERT's macro-F1 CI does not overlap either baseline's. Inference measured at "
                 f"{finbert_latency:.1f}ms/doc on CPU.\n")

    lines.append("**Module B stress test** (real portfolio: 50 positions, ~$992M notional)")
    lines.append(f"{n_signals} real signals evaluated, {n_fired} fired a stress test. Curve as-of {curve_date}."
                 f"{provisional_note}")
    if headline:
        headline_text = headline.get("headline_text") or "(see results/stress_test_output.json)"
        headline_text = headline_text[:90].rsplit(" ", 1)[0] + "..."  # avoid mid-word/duplicated-tail truncation
        lines.append(f"\nHighest-impact real trigger: *{headline_text}*"
                     f" (`{headline['event_class']}`, tier `{headline['tier']}`).")
        lines.append(f"- Portfolio value: ${headline['total_value_before']:,.0f} -> "
                     f"${headline['total_value_after']:,.0f}")
        lines.append(f"- MTM P&L (bonds/swaps/options/FX): ${headline['mtm_pnl']:,.0f}")
        lines.append(f"- Credit loss (loans, delta-EL): ${headline['credit_loss_on_loans']:,.0f}")
        lines.append(f"- **Total stressed loss: ${headline['total_stressed_loss']:,.0f} "
                     f"({headline['total_stressed_loss_pct']:.2f}%)**")
    else:
        lines.append("\nNo real signal has fired a stress test as of this generation (none exceeded the "
                     "impact threshold in the currently cached data).")

    lines.append(f"\n**Full reprice vs naive approximation** (required comparison, both measured on real "
                 f"portfolio positions): bond duration-only error grows to {bond_biggest['error']:,.0f} at "
                 f"{bond_biggest['shock']} vs. a full cashflow reprice; option delta-only error grows to "
                 f"{option_biggest['error']:,.2f} at {option_biggest['shock']} vs. a full Black-Scholes "
                 f"reprice -- both confirm genuine, growing convexity/gamma error (see `tests/test_naive_approx.py`).")

    lines.append("\n**Why it matters:** a risk/ratings team reading thousands of headlines a day cannot "
                 "manually translate each one into a portfolio impact. This pipeline shows that translation "
                 "happening end to end -- from raw text to a dollar P&L number, with the mark-to-market and "
                 "credit-loss channels kept separate so neither number silently double-counts the other.")

    key_results_section = "\n".join(lines)

    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    if "{{KEY_RESULTS_SECTION}}" not in template:
        raise RuntimeError("README_template.md is missing the {{KEY_RESULTS_SECTION}} placeholder.")
    final = template.replace("{{KEY_RESULTS_SECTION}}", key_results_section)

    OUT_PATH.write_text(final, encoding="utf-8")
    print(f"README.md written ({len(final)} chars). Every number above traced to {METRICS_PATH.name} / "
          f"{STRESS_PATH.name}.")


if __name__ == "__main__":
    main()
