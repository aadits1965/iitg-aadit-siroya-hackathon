#!/usr/bin/env python
"""Tiny interactive CLI for Aadit to hand-label data/eval/event_gold.csv.
Saves after every row, so it's safe to quit (Ctrl+C or 'q') and resume later.

The rule baseline's suggestion (`suggested_label_do_not_use_as_gold`) is
NEVER shown or offered as a shortcut -- labelling is fully blind to it. Every
label entered through this script is stamped `label_source = "human_blind"`,
so `scripts/score_event_classifier.py` can refuse to score any row that
isn't provably a blind human judgement.

Bug found 2026-10-19: an earlier version of this script showed the rule
suggestion on every row and offered 's' to accept it directly into
gold_label, with no record of which rows took that shortcut -- contaminating
the "human" gold set with the classifier's own predictions on an unknown
subset of rows. That 's' option is removed entirely, not just discouraged.
Use --fresh to discard all existing gold_label/label_source values (from
that contaminated run) and re-label every row from scratch.
"""
import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "data" / "eval" / "event_gold.csv"

CLASSES = ["Geopolitical", "Macroeconomic", "Credit Event", "Merger/Acquisition", "Product Launch", "Other"]
HUMAN_BLIND = "human_blind"


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fresh", action="store_true",
                         help="ignore existing gold_label/label_source values and re-label every row "
                              "from scratch, starting at row 1 (use this to discard a contaminated run)")
    return parser


def ensure_label_source_column(rows: list[dict], fieldnames: list[str]) -> list[str]:
    """Backward compatibility with a gold CSV written before label_source
    existed. Mutates `rows` in place; returns the (possibly extended)
    fieldnames list."""
    if "label_source" not in fieldnames:
        fieldnames = fieldnames + ["label_source"]
        for row in rows:
            row["label_source"] = ""
    return fieldnames


def main(argv=None, path: Path = PATH):
    args = build_arg_parser().parse_args(argv)

    if not path.exists():
        print(f"{path} not found. Run scripts/sample_event_gold.py first.")
        sys.exit(1)

    with path.open("r", newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    fieldnames = ensure_label_source_column(rows, list(rows[0].keys()))

    if args.fresh:
        for row in rows:
            row["gold_label"] = ""
            row["label_source"] = ""
        print(f"--fresh: discarded all existing gold_label/label_source values in {path}.\n")

    remaining = [r for r in rows if not r["gold_label"]]
    done = len(rows) - len(remaining)
    print(f"{done}/{len(rows)} already labelled. {len(remaining)} remaining.\n")
    print("Classes:")
    for i, c in enumerate(CLASSES, 1):
        print(f"  {i}. {c}")
    print("  q = save and quit\n")

    def save():
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    for row in rows:
        if row["gold_label"]:
            continue
        print("-" * 80)
        print(f"[{row['source']}] {row['published_at_utc']}")
        print(row["text"][:300])
        while True:
            choice = input("Label (1-6, q): ").strip().lower()
            if choice == "q":
                save()
                print("Saved. Resume anytime with the same command.")
                return
            if choice.isdigit() and 1 <= int(choice) <= len(CLASSES):
                row["gold_label"] = CLASSES[int(choice) - 1]
                row["label_source"] = HUMAN_BLIND
                break
            print("Invalid input.")
        save()

    print("\nAll rows labelled.")


if __name__ == "__main__":
    main()
