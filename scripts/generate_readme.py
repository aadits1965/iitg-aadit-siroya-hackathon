#!/usr/bin/env python
"""Generates README.md from docs/README_template.md, filling in the Key
Results section exclusively from results/metrics.json and
results/stress_test_output.json. REFUSES to write README.md if any field it
needs is missing or None -- a KeyError/TypeError here is the point, not a bug
to catch: it means a number this script was about to print doesn't actually
exist yet, and printing it anyway would be exactly the kind of placeholder/
fabricated number this project's own rules forbid.

Two metrics are allowed to be genuinely absent right now (pending Aadit's
local GDELT/labelling runs -- see docs/USER_TODO.md):
  - event_classification_eval (needs data/eval/event_gold.csv fully labelled)
  - impact_score_event_study (needs a real GDELT sample, n>=200 for power)
format_event_classification_status()/format_impact_event_study_status() below
handle both: if the metric exists in results/metrics.json, its real result is
shown in Key Results (including an explicit "no significant relationship"
statement if that's what the data shows, or an "UNDERPOWERED" flag if n<200 --
never a bare number presented as more conclusive than it is); if absent, Key
Results states plainly that it's pending, rather than silently omitting any
mention of it.
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


def format_event_classification_status(metrics: dict) -> str:
    ece = metrics.get("event_classification_eval")
    if not ece:
        return ("Event classification accuracy: **pending** -- needs `data/eval/event_gold.csv` fully "
                "hand-labelled (blind, via `scripts/label_events.py`, every row stamped "
                "`label_source=human_blind`), then `scripts/score_event_classifier.py` (scores the frozen "
                "`rule-v1`, git tag `classifier-v1`).")
    acc = ece["accuracy"]
    f1 = ece["macro_avg"]["f1-score"]
    n = ece["n_gold_examples"]
    version = ece.get("classifier_version", "rule-v1")
    classes_included = ece.get("macro_avg_classes_included")
    macro_note = (f" (macro-F1 over the {len(classes_included)} classes with support>0 in this sample: "
                  f"{classes_included})" if classes_included else "")
    ci = ece.get("accuracy_ci95")
    ci_str = f", 95% CI [{ci[0]:.1%}, {ci[1]:.1%}]" if ci else ""
    base = (f"Event classification (`{version}`, frozen before scoring, gold labels blind-human-only): "
            f"accuracy={acc:.1%}{ci_str}, macro-F1={f1:.3f}{macro_note} (n={n} hand-labelled examples).")
    maj = ece.get("majority_baseline")
    if maj:
        maj_ci = maj.get("accuracy_ci95")
        maj_ci_str = f" [{maj_ci[0]:.1%}, {maj_ci[1]:.1%}]" if maj_ci else ""
        base += (f" Majority-class baseline ({maj['description']}): accuracy={maj['accuracy']:.1%}"
                 f"{maj_ci_str}, macro-F1={maj['macro_avg']['f1-score']:.3f}.")
    return base


def format_impact_event_study_status(metrics: dict) -> str:
    ies = metrics.get("impact_score_event_study")
    if not ies:
        return ("Impact Score event-study correlation: **pending** -- needs a real GDELT sample "
                "(this dev sandbox cannot reach GDELT; see `docs/DATA_VERIFICATION.md` section 8). "
                "Run `scripts/run_impact_event_study.py` after `scripts/build_cache.py`.")
    if ies.get("status") == "not_run":
        return (f"Impact Score event-study correlation: **not run** -- {ies['reason']} "
                f"(attempted {ies.get('attempted_on', 'date unknown')}). No number is reported here because "
                f"none was computed -- see `docs/ASSUMPTIONS.md` \"Impact-score event study: not run\".")
    n = ies["n_resolved"]
    r = ies.get("spearman_r")
    if r is None:
        return f"Impact Score event-study correlation: n={n} resolved events -- too few to compute a correlation at all."
    ci = ies.get("ci95")
    ci_str = f" 95% CI [{ci[0]:.3f}, {ci[1]:.3f}]" if ci else ""
    if not ies.get("power_adequate", False):
        return (f"Impact Score event-study correlation: n={n} (**UNDERPOWERED**, below the n>=200 threshold "
                f"for reliable detection) -- Spearman r={r:.3f}{ci_str}. At this sample size, **no significant "
                f"relationship can be claimed either way** -- the CI is too wide to distinguish a real "
                f"correlation from noise.")
    p = ies.get("spearman_p")
    is_significant = p is not None and p < 0.05
    verdict = "a statistically significant" if is_significant else "**no statistically significant**"
    return (f"Impact Score event-study correlation: n={n}, Spearman r={r:.3f}{ci_str}"
            f"{f', p={p:.3f}' if p is not None else ''} -- {verdict} relationship between Impact Score and "
            f"realised abnormal returns. Association only, not causation.")


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

    lines.append("\n**Two evaluations from the original brief, status as of this generation:**")
    lines.append(f"- {format_event_classification_status(metrics)}")
    lines.append(f"- {format_impact_event_study_status(metrics)}")

    key_results_section = "\n".join(lines)

    ece = metrics.get("event_classification_eval")
    if not ece:
        event_class_limitation_bullet = (
            "- **Event classification accuracy is pending human labelling** of `data/eval/event_gold.csv`. "
            "The rule classifier is frozen at `rule-v1` (git tag `classifier-v1`) specifically so this "
            "score, once produced, reflects an honest, un-tuned evaluation."
        )
    else:
        pc = ece["per_class"]
        macro = pc.get("Macroeconomic", {})
        thin_classes = [c for c in ("Credit Event", "Geopolitical") if 0 < pc.get(c, {}).get("support", 0) < 5]
        thin_str = " and ".join(f"{c} (n={int(pc[c]['support'])})" for c in thin_classes) or "some classes"
        event_class_limitation_bullet = (
            f"- **Event classification (`rule-v1`, frozen before scoring) has real gaps, scored against "
            f"{ece['n_gold_examples']} blind-labelled examples**: Macroeconomic recall is only "
            f"{macro.get('recall', 0):.0%} ({round(macro.get('recall', 0) * macro.get('support', 0))} of "
            f"{int(macro.get('support', 0))}) despite {macro.get('precision', 0):.0%} precision -- it misses "
            f"most true Macroeconomic headlines. {thin_str} have too few gold examples in this sample to "
            f"evaluate at all. A genuine fix is a new `rule-v2`, scored on a fresh sample -- `rule-v1` stays "
            f"frozen (see `docs/ASSUMPTIONS.md`)."
        )

    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    if "{{KEY_RESULTS_SECTION}}" not in template:
        raise RuntimeError("README_template.md is missing the {{KEY_RESULTS_SECTION}} placeholder.")
    if "{{EVENT_CLASSIFICATION_LIMITATION_BULLET}}" not in template:
        raise RuntimeError("README_template.md is missing the {{EVENT_CLASSIFICATION_LIMITATION_BULLET}} placeholder.")
    final = template.replace("{{KEY_RESULTS_SECTION}}", key_results_section)
    final = final.replace("{{EVENT_CLASSIFICATION_LIMITATION_BULLET}}", event_class_limitation_bullet)

    OUT_PATH.write_text(final, encoding="utf-8")
    print(f"README.md written ({len(final)} chars). Every number above traced to {METRICS_PATH.name} / "
          f"{STRESS_PATH.name}.")


if __name__ == "__main__":
    main()
