"""Import blind human labels typed in Excel (data/eval/to_label.csv) into data/eval/event_gold.csv.

to_label.csv columns: doc_id, text, label  (label = 1..6, typed by the human labeller;
the file never contained the rule suggestion). Every imported row is stamped
label_source = "human_blind". Refuses to write anything if any row is missing,
invalid, duplicated, or does not match event_gold.csv exactly.
"""
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GOLD = ROOT / "data" / "eval" / "event_gold.csv"
LABELS = ROOT / "data" / "eval" / "to_label.csv"

CODE_TO_CLASS = {
    "1": "Geopolitical",
    "2": "Macroeconomic",
    "3": "Credit Event",
    "4": "Merger/Acquisition",
    "5": "Product Launch",
    "6": "Other",
}


def read_csv(path):
    # utf-8-sig handles the BOM that Excel's "CSV UTF-8" adds
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        return reader.fieldnames, list(reader)


def main():
    gold_fields, gold_rows = read_csv(GOLD)
    _, label_rows = read_csv(LABELS)

    errors = []
    labels = {}
    for i, r in enumerate(label_rows, start=2):  # row 1 is the header
        doc_id = (r.get("doc_id") or "").strip()
        code = (r.get("label") or "").strip()
        if code.endswith(".0"):  # Excel sometimes saves 6 as 6.0
            code = code[:-2]
        if not doc_id:
            errors.append(f"row {i}: empty doc_id")
            continue
        if code not in CODE_TO_CLASS:
            errors.append(f"row {i} ({doc_id}): label {code!r} is not 1-6")
            continue
        if doc_id in labels:
            errors.append(f"row {i}: duplicate doc_id {doc_id}")
            continue
        labels[doc_id] = CODE_TO_CLASS[code]

    gold_ids = [r["doc_id"] for r in gold_rows]
    missing = [d for d in gold_ids if d not in labels]
    extra = [d for d in labels if d not in set(gold_ids)]
    if missing:
        errors.append(f"{len(missing)} gold rows have no label, e.g. {missing[:3]}")
    if extra:
        errors.append(f"{len(extra)} labelled doc_ids not in event_gold.csv, e.g. {extra[:3]}")

    if errors:
        print("NOT IMPORTED -- fix these in to_label.csv first:")
        for e in errors[:30]:
            print("  -", e)
        sys.exit(1)

    fields = list(gold_fields)
    for col in ("gold_label", "label_source"):
        if col not in fields:
            fields.append(col)
    for r in gold_rows:
        r["gold_label"] = labels[r["doc_id"]]
        r["label_source"] = "human_blind"

    with open(GOLD, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(gold_rows)

    counts = {}
    for v in labels.values():
        counts[v] = counts.get(v, 0) + 1
    print(f"Imported {len(labels)} blind human labels into {GOLD}")
    for cls in CODE_TO_CLASS.values():
        print(f"  {cls:20s} {counts.get(cls, 0)}")


if __name__ == "__main__":
    main()
