#!/usr/bin/env python
"""Phase 3.2: sample a stratified pool of real cached documents into
data/eval/event_gold.csv for Aadit to hand-label. The rule classifier's own
suggestion is kept in a SEPARATE column (suggested_label_do_not_use_as_gold) and
must never be copied into gold_label or reported as a human label — see Phase 3
rules in the build prompt and docs/ASSUMPTIONS.md.
"""
import csv
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.ingestion.base import SourceAdapter  # noqa: E402
from src.nlp.event_classification import RuleBasedEventClassifier  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT_PATH = ROOT / "data" / "eval" / "event_gold.csv"
TARGET_N = 200
SEED = 42  # fixed, not tuned


def load_all_cached_docs() -> list:
    docs = []
    for path in [
        ROOT / "data" / "cache" / "news_gdelt.jsonl",
        ROOT / "data" / "cache" / "social_mastodon.jsonl",
        ROOT / "data" / "raw_samples" / "social_twitter_replay.jsonl",
    ]:
        if path.exists():
            docs.extend(list(SourceAdapter._read_jsonl(path)))
    return docs


def main():
    docs = load_all_cached_docs()
    if not docs:
        print("No cached documents found. Run scripts/build_cache.py first.")
        sys.exit(1)

    clf = RuleBasedEventClassifier()
    rng = random.Random(SEED)

    # Stratify loosely: bucket by the rule classifier's own guess so the sample
    # isn't dominated by "Other", then sample proportionally within a cap per
    # bucket so no single class swamps the 200-row budget.
    buckets: dict[str, list] = {}
    for d in docs:
        guess = clf.classify(d.text)
        buckets.setdefault(guess.event_class, []).append((d, guess))

    per_bucket_cap = max(TARGET_N // max(len(buckets), 1), 10)
    sampled = []
    for cls, items in buckets.items():
        rng.shuffle(items)
        sampled.extend(items[:per_bucket_cap])
    rng.shuffle(sampled)
    sampled = sampled[:TARGET_N]

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUT_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "doc_id", "source", "published_at_utc", "text",
            "suggested_label_do_not_use_as_gold", "gold_label",
        ])
        for d, guess in sampled:
            writer.writerow([
                d.doc_id, d.source, d.published_at_utc.isoformat(),
                d.text.replace("\n", " "), guess.event_class, "",
            ])

    print(f"Wrote {len(sampled)} rows to {OUT_PATH}")
    print("Class distribution sampled (by rule-baseline guess, for info only):")
    from collections import Counter
    print(Counter(g.event_class for _, g in sampled))
    print("\nNext: run `python scripts/label_events.py` to fill in gold_label by hand.")


if __name__ == "__main__":
    main()
