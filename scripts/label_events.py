#!/usr/bin/env python
"""Tiny interactive CLI for Aadit to hand-label data/eval/event_gold.csv.
Saves after every row, so it's safe to quit (Ctrl+C or 'q') and resume later.
The rule baseline's own suggestion is shown but NEVER auto-filled — you must
type a number (or 's' to explicitly accept the shown suggestion) for each row.
"""
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "data" / "eval" / "event_gold.csv"

CLASSES = ["Geopolitical", "Macroeconomic", "Credit Event", "Merger/Acquisition", "Product Launch", "Other"]


def main():
    if not PATH.exists():
        print(f"{PATH} not found. Run scripts/sample_event_gold.py first.")
        sys.exit(1)

    with PATH.open("r", newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    fieldnames = list(rows[0].keys())

    remaining = [r for r in rows if not r["gold_label"]]
    done = len(rows) - len(remaining)
    print(f"{done}/{len(rows)} already labelled. {len(remaining)} remaining.\n")
    print("Classes:")
    for i, c in enumerate(CLASSES, 1):
        print(f"  {i}. {c}")
    print("  s = accept the shown suggestion    q = save and quit\n")

    def save():
        with PATH.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    for row in rows:
        if row["gold_label"]:
            continue
        print("-" * 80)
        print(f"[{row['source']}] {row['published_at_utc']}")
        print(row["text"][:300])
        print(f"(rule baseline suggests: {row['suggested_label_do_not_use_as_gold']})")
        while True:
            choice = input("Label (1-6, s, q): ").strip().lower()
            if choice == "q":
                save()
                print("Saved. Resume anytime with the same command.")
                return
            if choice == "s":
                row["gold_label"] = row["suggested_label_do_not_use_as_gold"]
                break
            if choice.isdigit() and 1 <= int(choice) <= len(CLASSES):
                row["gold_label"] = CLASSES[int(choice) - 1]
                break
            print("Invalid input.")
        save()

    print("\nAll rows labelled.")


if __name__ == "__main__":
    main()
