"""Data-loading helpers for the Streamlit dashboard. Reads the same real
files the CLI scripts write to (results/signals.jsonl, results/metrics.json,
results/stress_test_output.json) -- the dashboard never recomputes anything
the scripts didn't already produce, so a number on screen is always traceable
to the script that wrote it."""
from __future__ import annotations

import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SIGNALS_PATH = ROOT / "results" / "signals.jsonl"
METRICS_PATH = ROOT / "results" / "metrics.json"
STRESS_OUTPUT_PATH = ROOT / "results" / "stress_test_output.json"
SCENARIOS_CONFIG_PATH = ROOT / "config" / "scenarios.yaml"


def load_signals() -> list[dict]:
    if not SIGNALS_PATH.exists():
        return []
    with SIGNALS_PATH.open("r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def load_metrics() -> dict:
    if not METRICS_PATH.exists():
        return {}
    return json.loads(METRICS_PATH.read_text(encoding="utf-8"))


def load_stress_output() -> dict:
    if not STRESS_OUTPUT_PATH.exists():
        return {}
    return json.loads(STRESS_OUTPUT_PATH.read_text(encoding="utf-8"))


def load_scenario_config() -> dict:
    with SCENARIOS_CONFIG_PATH.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


PORTFOLIO_PATH = ROOT / "data" / "synthetic" / "portfolio.csv"
EQUITY_CACHE_PATH = ROOT / "data" / "cache" / "market" / "equity_prices.csv"


def load_latest_equity_spot() -> dict[str, float]:
    import csv

    spot: dict[str, tuple[str, float]] = {}
    with EQUITY_CACHE_PATH.open("r", encoding="utf-8") as f:
        for row in csv.DictReader(line for line in f if not line.startswith("#")):
            ticker, d, px = row["ticker"], row["date"], float(row["close"])
            if ticker not in spot or d > spot[ticker][0]:
                spot[ticker] = (d, px)
    return {t: px for t, (d, px) in spot.items()}


def is_equity_data_provisional() -> bool:
    if not EQUITY_CACHE_PATH.exists():
        return False
    with EQUITY_CACHE_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.startswith("#"):
                break
            if line.lstrip("#").strip() == "provisional: true":
                return True
    return False
