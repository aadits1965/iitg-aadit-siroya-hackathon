#!/usr/bin/env python
"""Pull every source once and write cached JSONL snapshots to data/cache/ and
data/raw_samples/ for deterministic --demo runs. Run this from a normal network
connection (GDELT/RSS hosts are blocked from shared/datacenter IPs — see
docs/DATA_VERIFICATION.md section 8)."""
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.ingestion.pipeline import build_all_caches  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

if __name__ == "__main__":
    stats = build_all_caches()
    print("\n=== Ingestion summary ===")
    for s in stats:
        print(f"{s.source:16s} fetched={s.fetched:4d}  kept={s.kept_after_dedup:4d}  "
              f"dropped_exact={s.dropped_exact:3d}  dropped_fuzzy={s.dropped_fuzzy:3d}")
    if not stats:
        print("No sources returned data. Check network connectivity.")
        sys.exit(1)
