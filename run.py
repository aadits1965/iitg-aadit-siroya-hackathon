#!/usr/bin/env python
"""Single entry point for the whole demo: starts the signal API and the
dashboard against the already-committed results/, so the demo starts fast.

  python run.py --mode demo               (default) -- fully offline. Loads
                               the committed results/signals.jsonl and
                               results/stress_test_output.json as-is (no
                               FinBERT recompute) -- see --recompute below.
  python run.py --mode demo --recompute   -- rebuilds signals from
                               data/cache/ via the real engine (FinBERT
                               inference, ~60-75s) and re-runs the stress
                               test before launching. Needed after any code
                               change to src/nlp/ or src/modules/stress_test/.
  python run.py --mode live   -- first runs scripts/build_cache.py to pull
                               fresh data from a normal network (GDELT,
                               Mastodon, Treasury, Yahoo Finance -- all
                               confirmed unreachable from the dev sandbox
                               this was built in, see
                               docs/DATA_VERIFICATION.md), then ALWAYS
                               recomputes (fresh cache data needs fresh
                               signals -- --recompute is implied, not optional).

**Startup time**: with cached results/ already committed (the default),
starting the API alone measured at ~310ms once the process is running
(confirmed directly: launched `--no-dashboard`, polled /health with 0.5s
ticks). Total wall-clock from invoking this command to a working dashboard
in a browser is a few seconds -- Python interpreter start + uvicorn bind +
Streamlit's own startup, no model inference. With --recompute, budget the
full ~60-90s FinBERT run on top (first run downloads the model weights too,
~440MB, another one-time ~60-90s -- see scripts/run_engine.py).

If a live source fails mid-run (only relevant to --mode live), the affected
step is logged and the pipeline continues on whatever data it already has --
see src/ingestion/pipeline.py's per-source try/except blocks. Demo mode
(without --recompute) never touches the network or a model at all.
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
SIGNALS_PATH = ROOT / "results" / "signals.jsonl"
STRESS_PATH = ROOT / "results" / "stress_test_output.json"

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


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["demo", "live"], default="demo")
    parser.add_argument("--port", type=int, default=8501, help="Streamlit port")
    parser.add_argument("--api-port", type=int, default=8000, help="FastAPI signal-API port")
    parser.add_argument("--recompute", action="store_true",
                         help="rebuild signals from the cache via the real engine (FinBERT, ~60-75s) and "
                              "re-run the stress test, instead of loading the committed results/ as-is. "
                              "Implied automatically when --mode live is used.")
    parser.add_argument("--no-dashboard", action="store_true",
                         help="start the API but skip launching Streamlit (used by tests/scripting)")
    return parser


def should_recompute(args) -> bool:
    return args.mode == "live" or args.recompute


def main(argv=None):
    args = build_arg_parser().parse_args(argv)
    recompute = should_recompute(args)

    if args.mode == "live":
        run_step(["scripts/build_cache.py"], "Phase 1: building cache from live sources")

    if recompute:
        run_step(["scripts/run_engine.py"], "Phase 2: running the NLP risk engine over cached docs")
        run_step(["scripts/run_stress_test.py"], "Phase 4: running Module B stress test")
    else:
        if not SIGNALS_PATH.exists() or not STRESS_PATH.exists():
            logger.error(
                "results/signals.jsonl and/or results/stress_test_output.json not found. Run once with "
                "--recompute first (or they should already be committed to the repo)."
            )
            sys.exit(1)
        logger.info("=== Using committed results/signals.jsonl + results/stress_test_output.json as-is "
                     "(no FinBERT recompute -- pass --recompute to rebuild) ===")

    logger.info("=== Starting signal API on :%d ===", args.api_port)
    api_proc = subprocess.Popen(
        [PYTHON, "-m", "uvicorn", "src.api.main:app", "--host", "127.0.0.1", "--port", str(args.api_port)],
        cwd=ROOT, env=SUBPROCESS_ENV,
    )
    atexit.register(api_proc.terminate)

    if args.no_dashboard:
        # Block here rather than returning immediately -- an early return would
        # let this process exit right after starting api_proc, which fires the
        # atexit handler and kills the API within milliseconds of starting it
        # (a real bug this script's own startup-time test caught: the API
        # looked like it was "hanging", but it had actually already been
        # torn down before the first health-check poll landed).
        logger.info("=== --no-dashboard: API running at :%d, Ctrl+C to stop ===", args.api_port)
        try:
            api_proc.wait()
        except KeyboardInterrupt:
            pass
        return api_proc

    logger.info("=== Launching dashboard on :%d ===", args.port)
    try:
        subprocess.run(
            [PYTHON, "-m", "streamlit", "run", "src/dashboard/app.py",
             "--server.port", str(args.port), "--server.headless", "true"],
            cwd=ROOT, env=SUBPROCESS_ENV,
        )
    finally:
        api_proc.terminate()
    return None


if __name__ == "__main__":
    main()
