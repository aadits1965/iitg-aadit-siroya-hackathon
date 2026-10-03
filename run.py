#!/usr/bin/env python
"""Single entry point for the whole demo: builds signals from the cache, runs
the stress test, starts the signal API, and launches the dashboard.

  python run.py --mode demo   (default) -- fully offline, deterministic.
                               Uses whatever is already in data/cache/ and
                               data/raw_samples/ (committed to the repo).
  python run.py --mode live   -- first runs scripts/build_cache.py to pull
                               fresh data from a normal network (GDELT,
                               Mastodon, Treasury, Yahoo Finance -- all
                               confirmed unreachable from the dev sandbox
                               this was built in, see
                               docs/DATA_VERIFICATION.md), then proceeds as
                               --mode demo.

First run downloads model weights (~440MB for FinBERT) -- a one-time cost of
roughly 60-90s on a normal connection, logged by scripts/run_engine.py.
Subsequent runs reuse the cached weights (~87-170ms/doc inference instead).

If a live source fails mid-run (only relevant to --mode live), the affected
step is logged and the pipeline continues on whatever data it already has --
see src/ingestion/pipeline.py's per-source try/except blocks. Demo mode never
touches the network beyond that one-time model download.
"""
import argparse
import atexit
import logging
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PYTHON = sys.executable

# Real headline/tweet text can contain emoji and other non-ASCII characters.
# Windows' default console codepage (cp1252) can't encode them, which crashed
# a child script's print() with UnicodeEncodeError and made this orchestrator
# treat a cosmetic console-output issue as a hard pipeline failure. Forcing
# UTF-8 I/O for every subprocess step fixes this at the root rather than
# patching each script's print statements individually.
SUBPROCESS_ENV = {**os.environ, "PYTHONIOENCODING": "utf-8"}

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("run")


def run_step(args: list[str], description: str) -> None:
    logger.info("=== %s ===", description)
    result = subprocess.run([PYTHON] + args, cwd=ROOT, env=SUBPROCESS_ENV)
    if result.returncode != 0:
        logger.error("%s failed (exit code %d) -- stopping.", description, result.returncode)
        sys.exit(result.returncode)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["demo", "live"], default="demo")
    parser.add_argument("--port", type=int, default=8501, help="Streamlit port")
    parser.add_argument("--api-port", type=int, default=8000, help="FastAPI signal-API port")
    parser.add_argument("--skip-pipeline", action="store_true",
                         help="skip rebuilding signals/stress-test output, just launch the dashboard "
                              "against whatever is already in results/")
    args = parser.parse_args()

    if args.mode == "live":
        run_step(["scripts/build_cache.py"], "Phase 1: building cache from live sources")

    if not args.skip_pipeline:
        run_step(["scripts/run_engine.py"], "Phase 2: running the NLP risk engine over cached docs")
        run_step(["scripts/run_stress_test.py"], "Phase 4: running Module B stress test")

    logger.info("=== Starting signal API on :%d ===", args.api_port)
    api_proc = subprocess.Popen(
        [PYTHON, "-m", "uvicorn", "src.api.main:app", "--host", "127.0.0.1", "--port", str(args.api_port)],
        cwd=ROOT, env=SUBPROCESS_ENV,
    )
    atexit.register(api_proc.terminate)

    logger.info("=== Launching dashboard on :%d ===", args.port)
    try:
        subprocess.run(
            [PYTHON, "-m", "streamlit", "run", "src/dashboard/app.py",
             "--server.port", str(args.port), "--server.headless", "true"],
            cwd=ROOT, env=SUBPROCESS_ENV,
        )
    finally:
        api_proc.terminate()


if __name__ == "__main__":
    main()
