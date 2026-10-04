#!/usr/bin/env python
"""Scores the FROZEN rule-v1 classifier (see docs/ASSUMPTIONS.md "Event
classifier: frozen at rule-v1") against data/eval/event_gold.csv, once Aadit
has hand-labelled it. Refuses to run (and refuses to write anything to
results/metrics.json) if labelling isn't complete -- reporting partial/
placeholder numbers would violate the project's own no-fabrication rule.

This script must NEVER be edited to tune RULE_KEYWORDS/CREDIT_MARKET_INDICATORS
based on what it reports -- that would be exactly the eval-set-tuning the
freeze exists to prevent. A rule change is a new version (rule-v2), scored
separately, never re-scored against the same gold rows rule-v1 used.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402
from sklearn.metrics import classification_report, confusion_matrix  # noqa: E402

from src.nlp.event_classification import EVENT_CLASSES, RULE_CLASSIFIER_VERSION, RuleBasedEventClassifier  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
GOLD_PATH = ROOT / "data" / "eval" / "event_gold.csv"
METRICS_PATH = ROOT / "results" / "metrics.json"


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

    invalid = ~gold_df["gold_label"].isin(EVENT_CLASSES)
    if invalid.any():
        print(f"REFUSING TO SCORE: {invalid.sum()} rows have a gold_label not in {EVENT_CLASSES}: "
              f"{gold_df.loc[invalid, 'gold_label'].unique().tolist()}")
        sys.exit(1)

    clf = RuleBasedEventClassifier()
    y_true = gold_df["gold_label"].tolist()
    y_pred = [clf.classify(text).event_class for text in gold_df["text"]]

    report = classification_report(y_true, y_pred, labels=EVENT_CLASSES, output_dict=True, zero_division=0)
    cm = confusion_matrix(y_true, y_pred, labels=EVENT_CLASSES)

    results = {
        "classifier_version": RULE_CLASSIFIER_VERSION,
        "n_gold_examples": len(gold_df),
        "per_class": {cls: report[cls] for cls in EVENT_CLASSES},
        "macro_avg": report["macro avg"],
        "accuracy": report["accuracy"],
        "confusion_matrix": {"labels": EVENT_CLASSES, "matrix": cm.tolist()},
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

    print(f"Scored {RULE_CLASSIFIER_VERSION} against {len(gold_df)} gold-labelled examples.")
    print(f"Accuracy: {report['accuracy']:.3f}  Macro-F1: {report['macro avg']['f1-score']:.3f}")
    print(json.dumps(results["per_class"], indent=2))
    print(f"\nWritten to {METRICS_PATH}")


if __name__ == "__main__":
    main()
