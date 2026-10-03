#!/usr/bin/env python
"""Phase 3.1: run sentiment evaluation and merge the result into results/metrics.json.
Never overwrites unrelated keys already in that file."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.eval.sentiment_eval import run  # noqa: E402

METRICS_PATH = Path(__file__).resolve().parents[1] / "results" / "metrics.json"


def main():
    results = run(limit=2000, include_finbert=True)

    existing = {}
    if METRICS_PATH.exists():
        existing = json.loads(METRICS_PATH.read_text(encoding="utf-8"))
    existing["sentiment_eval"] = results
    METRICS_PATH.parent.mkdir(parents=True, exist_ok=True)
    METRICS_PATH.write_text(json.dumps(existing, indent=2), encoding="utf-8")

    print(json.dumps(results, indent=2))
    print(f"\nWritten to {METRICS_PATH}")


if __name__ == "__main__":
    main()
