"""Demo mode must start fast: by default it loads the committed
results/signals.jsonl and results/stress_test_output.json as-is (no FinBERT
recompute), only rebuilding when --recompute (or --mode live) is passed.

Two tests:
  - fast (always runs): the argument-parsing/branching logic itself, with
    subprocess calls mocked out.
  - real (opt-in, RUN_SLOW_TESTS=1): actually launches `run.py --mode demo
    --no-dashboard` as a subprocess and times how long until the API
    responds, to catch a real regression in startup time, not just the
    branching logic.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import run as run_module  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]

# Generous: actual measured startup is a few seconds (just uvicorn + streamlit
# process spin-up, no model inference) -- this threshold exists to catch a
# real regression (e.g. --recompute silently becoming the default again), not
# to be a tight performance budget.
STARTUP_BUDGET_SECONDS = 20


class TestRecomputeDecision:
    def test_demo_without_recompute_flag_does_not_recompute(self):
        args = run_module.build_arg_parser().parse_args(["--mode", "demo"])
        assert run_module.should_recompute(args) is False

    def test_demo_with_recompute_flag_does_recompute(self):
        args = run_module.build_arg_parser().parse_args(["--mode", "demo", "--recompute"])
        assert run_module.should_recompute(args) is True

    def test_live_mode_always_recomputes_even_without_flag(self):
        args = run_module.build_arg_parser().parse_args(["--mode", "live"])
        assert run_module.should_recompute(args) is True


class TestMainSkipsEngineRebuildByDefault:
    def test_default_demo_mode_never_calls_run_engine_or_stress_test(self):
        with patch.object(run_module, "run_step") as mock_run_step, \
             patch.object(run_module.subprocess, "Popen") as mock_popen, \
             patch.object(run_module, "SIGNALS_PATH") as mock_signals, \
             patch.object(run_module, "STRESS_PATH") as mock_stress:
            mock_signals.exists.return_value = True
            mock_stress.exists.return_value = True
            mock_popen.return_value = MagicMock()

            run_module.main(["--mode", "demo", "--no-dashboard"])

            mock_run_step.assert_not_called()
            mock_popen.assert_called_once()

    def test_recompute_flag_calls_run_engine_and_stress_test(self):
        with patch.object(run_module, "run_step") as mock_run_step, \
             patch.object(run_module.subprocess, "Popen") as mock_popen:
            mock_popen.return_value = MagicMock()

            run_module.main(["--mode", "demo", "--recompute", "--no-dashboard"])

            calls = [c.args[0] for c in mock_run_step.call_args_list]
            assert ["scripts/run_engine.py"] in calls
            assert ["scripts/run_stress_test.py"] in calls

    def test_missing_results_without_recompute_exits_with_error(self):
        with patch.object(run_module, "SIGNALS_PATH") as mock_signals:
            mock_signals.exists.return_value = False
            with pytest.raises(SystemExit):
                run_module.main(["--mode", "demo", "--no-dashboard"])


@pytest.mark.skipif(not os.environ.get("RUN_SLOW_TESTS"), reason="launches a real subprocess; set RUN_SLOW_TESTS=1")
class TestRealStartupTime:
    def test_demo_mode_api_responds_within_budget(self):
        env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
        t0 = time.perf_counter()
        proc = subprocess.Popen(
            [sys.executable, "run.py", "--mode", "demo", "--no-dashboard", "--api-port", "8099"],
            cwd=ROOT, env=env,
        )
        try:
            import urllib.request
            deadline = t0 + STARTUP_BUDGET_SECONDS
            last_error = None
            while time.perf_counter() < deadline:
                try:
                    with urllib.request.urlopen("http://127.0.0.1:8099/health", timeout=1) as resp:
                        if resp.status == 200:
                            elapsed = time.perf_counter() - t0
                            print(f"\nReal measured startup time: {elapsed:.2f}s")
                            assert elapsed < STARTUP_BUDGET_SECONDS
                            return
                except Exception as e:  # noqa: BLE001
                    last_error = e
                    time.sleep(0.3)
            pytest.fail(f"API did not respond within {STARTUP_BUDGET_SECONDS}s (last error: {last_error})")
        finally:
            proc.terminate()
            proc.wait(timeout=10)
