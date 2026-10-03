"""Trigger engine (Phase 4.3): scans signals (from results/signals.jsonl or the
API) and decides which ones fire a stress test. Per-class threshold override,
cooldown/dedup so one story doesn't trigger the same entity/event cluster
repeatedly -- this mirrors (and reuses the same cooldown window as) the NLP
engine's own novelty tracking in src/nlp/engine.py, applied here independently
so Module B's trigger logic doesn't silently depend on engine internals."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import yaml

SCENARIOS_CONFIG_PATH = Path(__file__).resolve().parents[3] / "config" / "scenarios.yaml"
SIGNALS_PATH = Path(__file__).resolve().parents[3] / "results" / "signals.jsonl"


@dataclass
class TriggerDecision:
    signal_id: str
    fired: bool
    reason: str
    event_class: str
    impact_score: float
    tickers: list
    sectors: list
    countries: list
    created_at_utc: datetime


def load_trigger_config() -> dict:
    with SCENARIOS_CONFIG_PATH.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    return cfg["trigger"]


def evaluate_signals(signals: list[dict], threshold: float | None = None, cooldown_hours: float | None = None) -> list[TriggerDecision]:
    trigger_cfg = load_trigger_config()
    threshold = threshold if threshold is not None else trigger_cfg["default_impact_threshold"]
    cooldown = timedelta(hours=cooldown_hours if cooldown_hours is not None else trigger_cfg["cooldown_hours"])

    ordered = sorted(signals, key=lambda s: s["created_at_utc"])
    last_fired: dict[tuple, datetime] = {}
    decisions = []

    for sig in ordered:
        impact = sig["impact"]["score"]
        event_class = sig["event"]["event_class"]
        created_at = datetime.fromisoformat(sig["created_at_utc"])
        cluster_key = (tuple(sorted(sig["tickers"])) or tuple(sorted(sig.get("macro_tags", []))), event_class)

        if impact <= threshold:
            decisions.append(TriggerDecision(
                sig["signal_id"], False, f"impact {impact} <= threshold {threshold}",
                event_class, impact, sig["tickers"], sig.get("sectors", []), sig.get("countries", []), created_at,
            ))
            continue

        prior = last_fired.get(cluster_key)
        if prior is not None and (created_at - prior) <= cooldown:
            decisions.append(TriggerDecision(
                sig["signal_id"], False, f"cooldown active ({cooldown}) since last fire for this cluster",
                event_class, impact, sig["tickers"], sig.get("sectors", []), sig.get("countries", []), created_at,
            ))
            continue

        last_fired[cluster_key] = created_at
        decisions.append(TriggerDecision(
            sig["signal_id"], True, f"impact {impact} > threshold {threshold}, cooldown clear",
            event_class, impact, sig["tickers"], sig.get("sectors", []), sig.get("countries", []), created_at,
        ))

    return decisions


def load_signals_from_file(path: Path = SIGNALS_PATH) -> list[dict]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]
