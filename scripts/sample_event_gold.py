#!/usr/bin/env python
"""Phase 3.2: sample a stratified pool of real cached documents into
data/eval/event_gold.csv. The rule classifier's own suggestion is kept in a
SEPARATE column (suggested_label_do_not_use_as_gold) and must never be copied
into gold_label or reported as a human label — see Phase 3 rules in the build
prompt and docs/ASSUMPTIONS.md.

Targets ~200 rows total with at least 20 per class where that many are
available in the cached doc pool (classes with fewer available documents just
contribute all of them; the shortfall is redistributed to classes with surplus
so the total still approaches TARGET_N when the data allows it).

Do NOT ask Aadit to label this until after he's run scripts/build_cache.py --
re-run this script first so the sample includes the GDELT news channel (much
better class coverage, especially Product Launch / Merger-Acquisition, which
are rare in the Mastodon/Twitter-only pool) before spending his labelling time.
"""
import csv
import random
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.ingestion.base import SourceAdapter  # noqa: E402
from src.nlp.event_classification import EVENT_CLASSES, RuleBasedEventClassifier  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT_PATH = ROOT / "data" / "eval" / "event_gold.csv"
TARGET_N = 200
MIN_PER_CLASS = 20
SEED = 42  # fixed, not tuned


def load_all_cached_docs() -> list:
    docs = []
    for path in [
        ROOT / "data" / "cache" / "news_gdelt.jsonl",
        ROOT / "data" / "cache" / "news_gdelt_event_study.jsonl",
        ROOT / "data" / "cache" / "social_mastodon.jsonl",
        ROOT / "data" / "raw_samples" / "social_twitter_replay.jsonl",
    ]:
        if path.exists():
            docs.extend(list(SourceAdapter._read_jsonl(path)))
    return docs


def stratified_sample(buckets: dict[str, list], target_n: int, min_per_class: int, rng: random.Random) -> list:
    for items in buckets.values():
        rng.shuffle(items)

    per_class_target = max(target_n // max(len(EVENT_CLASSES), 1), min_per_class)
    taken: dict[str, int] = {}
    sampled = []
    for cls in EVENT_CLASSES:
        items = buckets.get(cls, [])
        take = min(len(items), per_class_target)
        sampled.extend(items[:take])
        taken[cls] = take

    # Redistribute shortfall (classes with fewer than per_class_target available)
    # to classes with surplus, round-robin, until target_n is hit or surplus runs out.
    remaining_budget = target_n - len(sampled)
    if remaining_budget > 0:
        surplus_pools = {
            cls: buckets.get(cls, [])[taken[cls]:] for cls in EVENT_CLASSES
        }
        changed = True
        while remaining_budget > 0 and changed:
            changed = False
            for cls in EVENT_CLASSES:
                if remaining_budget <= 0:
                    break
                pool = surplus_pools[cls]
                if pool:
                    sampled.append(pool.pop(0))
                    remaining_budget -= 1
                    changed = True

    rng.shuffle(sampled)
    return sampled[:target_n]


def main():
    docs = load_all_cached_docs()
    if not docs:
        print("No cached documents found. Run scripts/build_cache.py first.")
        sys.exit(1)

    clf = RuleBasedEventClassifier()
    rng = random.Random(SEED)

    buckets: dict[str, list] = {cls: [] for cls in EVENT_CLASSES}
    for d in docs:
        guess = clf.classify(d.text)
        buckets[guess.event_class].append((d, guess))

    print("Available documents per rule-baseline-guessed class (before sampling):")
    print({cls: len(items) for cls, items in buckets.items()})

    sampled = stratified_sample(buckets, TARGET_N, MIN_PER_CLASS, rng)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUT_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "doc_id", "source", "published_at_utc", "text",
            "suggested_label_do_not_use_as_gold", "gold_label", "label_source",
        ])
        for d, guess in sampled:
            writer.writerow([
                d.doc_id, d.source, d.published_at_utc.isoformat(),
                d.text.replace("\n", " "), guess.event_class, "", "",
            ])

    print(f"\nWrote {len(sampled)} rows to {OUT_PATH}")
    print("Class distribution sampled (by rule-baseline guess, for info only):")
    print(Counter(g.event_class for _, g in sampled))
    print("\nNext: run `python scripts/label_events.py` to fill in gold_label by hand.")


if __name__ == "__main__":
    main()
