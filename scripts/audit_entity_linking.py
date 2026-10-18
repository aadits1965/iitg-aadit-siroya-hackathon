#!/usr/bin/env python
"""Phase 4 review: samples 50 real documents that link to >=1 ticker in the
widened 80-ticker event-study universe and writes them to
data/eval/entity_linking_audit.csv for manual precision labelling (the AI
assistant labelled the committed version by reading each row -- see
docs/DATA_VERIFICATION.md section 11 for the verdicts, the provenance note,
and the two bugs this audit caught: the "Target" bare-alias collision with
"price target", and the "ups"/UPS verb collision -- both now fixed in
src/nlp/entity_linking.py).
"""
import csv
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.ingestion.base import SourceAdapter  # noqa: E402
from src.nlp.entity_linking import EntityLinker, load_universe  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT_PATH = ROOT / "data" / "eval" / "entity_linking_audit.csv"
SAMPLE_N = 50
SEED = 42


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


def main():
    docs = load_all_cached_docs()
    wide_universe = load_universe(ROOT / "data" / "universe_event_study.csv")
    linker = EntityLinker(universe=wide_universe)

    linked = [(d, linker.link(d.text)) for d in docs]
    linked = [(d, m) for d, m in linked if m.tickers]
    print(f"{len(linked)} / {len(docs)} docs link to >=1 wide-universe ticker")

    rng = random.Random(SEED)
    rng.shuffle(linked)
    sample = linked[:SAMPLE_N]

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUT_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["doc_id", "source", "text", "linked_tickers", "verdict_tp_or_fp", "note"])
        for d, m in sample:
            writer.writerow([d.doc_id, d.source, d.text.replace("\n", " "), "|".join(m.tickers), "", ""])

    print(f"Wrote {len(sample)} rows to {OUT_PATH} -- fill in verdict_tp_or_fp by hand.")


if __name__ == "__main__":
    main()
