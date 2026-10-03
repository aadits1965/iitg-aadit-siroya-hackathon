"""Smoke tests for the dashboard's data-loading helpers against real files."""
from __future__ import annotations

from src.dashboard.data import (
    is_equity_data_provisional,
    load_latest_equity_spot,
    load_metrics,
    load_scenario_config,
    load_signals,
    load_stress_output,
)


class TestLoaders:
    def test_load_signals_returns_list_of_dicts(self):
        signals = load_signals()
        assert isinstance(signals, list)
        if signals:
            assert "signal_id" in signals[0]
            assert "impact" in signals[0]

    def test_load_metrics_returns_dict(self):
        metrics = load_metrics()
        assert isinstance(metrics, dict)

    def test_load_stress_output_returns_dict(self):
        out = load_stress_output()
        assert isinstance(out, dict)

    def test_load_scenario_config_has_required_keys(self):
        cfg = load_scenario_config()
        assert "severity_tiers" in cfg
        assert "event_class_mapping" in cfg
        assert "config_version" in cfg

    def test_load_latest_equity_spot_returns_floats(self):
        spot = load_latest_equity_spot()
        assert isinstance(spot, dict)
        for ticker, price in spot.items():
            assert isinstance(price, float)
            assert price > 0

    def test_is_equity_data_provisional_returns_bool(self):
        assert isinstance(is_equity_data_provisional(), bool)
