#!/usr/bin/env python
"""Scores the FROZEN rule-v1 classifier (see docs/ASSUMPTIONS.md "Event
classifier: frozen at rule-v1") against data/eval/event_gold.csv, once Aadit
has hand-labelled it. Refuses to run (and refuses to write anything to
results/metrics.json) if labelling isn't complete, or if any row isn't
provably a blind human judgement -- reporting partial/placeholder/
contaminated numbers would violate the project's own no-fabrication rule.

This script must NEVER be edited to tune RULE_KEYWORDS/CREDIT_MARKET_INDICATORS
based on what it reports -- that would be exactly the eval-set-tuning the
freeze exists to prevent. A rule change is a new version (rule-v2), scored
separately, never re-scored against the same gold rows rule-v1 used.
"""
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402
from sklearn.metrics import classification_report, confusion_matrix  # noqa: E402

from src.nlp.event_classification import EVENT_CLASSES, RULE_CLASSIFIER_VERSION, RuleBasedEventClassifier  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
GOLD_PATH = ROOT / "data" / "eval" / "event_gold.csv"
METRICS_PATH = ROOT / "results" / "metrics.json"
HUMAN_BLIND = "human_blind"


def wilson_ci(successes: int, n: int, z: float = 1.959963985) -> tuple[float, float]:
    """Closed-form Wilson score interval (statsmodels isn't installed in this
    environment, same reasoning as the entity-linking audit in
    docs/DATA_VERIFICATION.md section 13)."""
    if n == 0:
        return (0.0, 0.0)
    phat = successes / n
    denom = 1 + z**2 / n
    center = phat + z**2 / (2 * n)
    margin = z * math.sqrt(phat * (1 - phat) / n + z**2 / (4 * n**2))
    return (max(0.0, (center - margin) / denom), min(1.0, (center + margin) / denom))


def macro_avg_over_present_classes(y_true: list, y_pred: list, all_classes: list[str]) -> tuple[dict, list[str]]:
    """Bug fixed 2026-10-19: classification_report's macro avg, when given
    `labels=all_classes`, averages in every class in that list -- including
    ones with ZERO support in y_true, whose F1 is 0 by `zero_division=0`.
    That drags macro-F1 down for classes that simply never appear in this
    particular gold sample (e.g. this project's gold set has had zero
    "Product Launch" examples), which is not a real classifier failure.
    Restricting `labels=` to only classes present in y_true fixes this --
    the per-class breakdown (computed separately, over ALL classes) still
    shows support=0 for any absent class, so nothing is hidden."""
    present_classes = [c for c in all_classes if c in set(y_true)]
    report = classification_report(y_true, y_pred, labels=present_classes, output_dict=True, zero_division=0)
    return report["macro avg"], present_classes


def main():
    if not GOLD_PATH.exists():
        print(f"{GOLD_PATH} not found. Run scripts/sample_event_gold.py first.")
        sys.exit(1)

    gold_df = pd.read_csv(GOLD_PATH)
    if "gold_label" not in gold_df.columns:
        print(f"{GOLD_PATH} has no gold_label column -- malformed file.")
        sys.exit(1)

    unlabelled = gold_df["gold_label"].isna().sum()
    if unlabelled > 0:
        print(f"REFUSING TO SCORE: {unlabelled} / {len(gold_df)} rows in {GOLD_PATH} are not yet labelled.")
        print("Run `python scripts/label_events.py` to finish labelling first -- see docs/USER_TODO.md.")
        print("Nothing was written to results/metrics.json.")
        sys.exit(1)

    if "label_source" not in gold_df.columns:
        print(f"REFUSING TO SCORE: {GOLD_PATH} has no label_source column -- cannot prove any label is a "
              f"blind human judgement (this is the exact shape of the file before the 2026-10-19 "
              f"contamination fix -- see docs/ASSUMPTIONS.md). Re-run `python scripts/label_events.py "
              f"--fresh` to re-label from scratch with label_source recorded.")
        sys.exit(1)

    not_human_blind = (gold_df["label_source"] != HUMAN_BLIND).sum()
    if not_human_blind > 0:
        print(f"REFUSING TO SCORE: {not_human_blind} / {len(gold_df)} rows have label_source != {HUMAN_BLIND!r} "
              f"(empty, or some other value) -- cannot prove every gold label is a blind human judgement, "
              f"not the rule classifier's own prediction accepted as a shortcut. Re-run "
              f"`python scripts/label_events.py --fresh` to re-label every row from scratch.")
        sys.exit(1)

    invalid = ~gold_df["gold_label"].isin(EVENT_CLASSES)
    if invalid.any():
        print(f"REFUSING TO SCORE: {invalid.sum()} rows have a gold_label not in {EVENT_CLASSES}: "
              f"{gold_df.loc[invalid, 'gold_label'].unique().tolist()}")
        sys.exit(1)

    clf = RuleBasedEventClassifier()
    y_true = gold_df["gold_label"].tolist()
    y_pred = [clf.classify(text).event_class for text in gold_df["text"]]
    n = len(gold_df)

    report = classification_report(y_true, y_pred, labels=EVENT_CLASSES, output_dict=True, zero_division=0)
    macro_avg, present_classes = macro_avg_over_present_classes(y_true, y_pred, EVENT_CLASSES)
    cm = confusion_matrix(y_true, y_pred, labels=EVENT_CLASSES)

    accuracy = report["accuracy"]
    n_correct = round(accuracy * n)
    accuracy_ci95 = wilson_ci(n_correct, n)

    # Majority-class ("always Other") baseline -- same gold set, same metric
    # definitions, so rule-v1's numbers above can be read against a real
    # floor rather than in isolation.
    y_pred_majority = ["Other"] * n
    majority_report = classification_report(y_true, y_pred_majority, labels=EVENT_CLASSES,
                                              output_dict=True, zero_division=0)
    majority_macro_avg, majority_present_classes = macro_avg_over_present_classes(
        y_true, y_pred_majority, EVENT_CLASSES)
    majority_accuracy = majority_report["accuracy"]
    majority_n_correct = round(majority_accuracy * n)
    majority_accuracy_ci95 = wilson_ci(majority_n_correct, n)

    results = {
        "classifier_version": RULE_CLASSIFIER_VERSION,
        "n_gold_examples": n,
        "per_class": {cls: report[cls] for cls in EVENT_CLASSES},
        "macro_avg": macro_avg,
        "macro_avg_classes_included": present_classes,
        "accuracy": accuracy,
        "accuracy_ci95": list(accuracy_ci95),
        "confusion_matrix": {"labels": EVENT_CLASSES, "matrix": cm.tolist()},
        "majority_baseline": {
            "description": "always predicts 'Other'",
            "accuracy": majority_accuracy,
            "accuracy_ci95": list(majority_accuracy_ci95),
            "macro_avg": majority_macro_avg,
            "macro_avg_classes_included": majority_present_classes,
        },
    }

    existing = {}
    if METRICS_PATH.exists():
        existing = json.loads(METRICS_PATH.read_text(encoding="utf-8"))
    if "event_classification_eval" in existing:
        print(f"WARNING: results/metrics.json already has an event_classification_eval block "
              f"(version {existing['event_classification_eval'].get('classifier_version')}). "
              f"Overwriting with this run's result -- if that prior result was rule-v1 and this is also "
              f"rule-v1, this should be identical (the classifier is frozen); if this is testing a rule-v2, "
              f"it must be stored under a different key, not silently replace v1's.")
    existing["event_classification_eval"] = results
    METRICS_PATH.parent.mkdir(parents=True, exist_ok=True)
    METRICS_PATH.write_text(json.dumps(existing, indent=2), encoding="utf-8")

    print(f"Scored {RULE_CLASSIFIER_VERSION} against {n} gold-labelled examples (all label_source={HUMAN_BLIND!r}).")
    print(f"Accuracy: {accuracy:.3f} (95% CI {accuracy_ci95[0]:.3f}-{accuracy_ci95[1]:.3f})  "
          f"Macro-F1: {macro_avg['f1-score']:.3f} (over {len(present_classes)} classes with support>0: "
          f"{present_classes})")
    print(f"Majority-class ('always Other') baseline -- Accuracy: {majority_accuracy:.3f} "
          f"(95% CI {majority_accuracy_ci95[0]:.3f}-{majority_accuracy_ci95[1]:.3f})  "
          f"Macro-F1: {majority_macro_avg['f1-score']:.3f}")
    print(json.dumps(results["per_class"], indent=2))
    print(f"\nWritten to {METRICS_PATH}")


if __name__ == "__main__":
    main()
