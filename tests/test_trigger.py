"""Phase 4.3: trigger engine -- threshold filtering and cooldown/dedup."""
from __future__ import annotations

from src.modules.stress_test.trigger import evaluate_signals


def _signal(sig_id, impact, event_class, tickers, created_at):
    return {
        "signal_id": sig_id,
        "created_at_utc": created_at,
        "impact": {"score": impact},
        "event": {"event_class": event_class},
        "tickers": tickers,
        "sectors": [],
        "countries": [],
        "macro_tags": [],
    }


class TestThreshold:
    def test_below_threshold_does_not_fire(self):
        signals = [_signal("s1", 5.0, "Credit Event", ["AAPL"], "2026-01-01T00:00:00+00:00")]
        decisions = evaluate_signals(signals, threshold=7.0)
        assert decisions[0].fired is False

    def test_above_threshold_fires(self):
        signals = [_signal("s1", 8.0, "Credit Event", ["AAPL"], "2026-01-01T00:00:00+00:00")]
        decisions = evaluate_signals(signals, threshold=7.0)
        assert decisions[0].fired is True

    def test_exactly_at_threshold_does_not_fire(self):
        signals = [_signal("s1", 7.0, "Credit Event", ["AAPL"], "2026-01-01T00:00:00+00:00")]
        decisions = evaluate_signals(signals, threshold=7.0)
        assert decisions[0].fired is False  # strictly greater than, matching the brief's "Impact Score > 7"


class TestCooldown:
    def test_second_high_impact_signal_same_cluster_within_cooldown_suppressed(self):
        signals = [
            _signal("s1", 9.0, "Credit Event", ["AAPL"], "2026-01-01T00:00:00+00:00"),
            _signal("s2", 9.0, "Credit Event", ["AAPL"], "2026-01-01T02:00:00+00:00"),  # 2h later, within 6h cooldown
        ]
        decisions = evaluate_signals(signals, threshold=7.0, cooldown_hours=6.0)
        assert decisions[0].fired is True
        assert decisions[1].fired is False
        assert "cooldown" in decisions[1].reason

    def test_second_signal_outside_cooldown_fires_again(self):
        signals = [
            _signal("s1", 9.0, "Credit Event", ["AAPL"], "2026-01-01T00:00:00+00:00"),
            _signal("s2", 9.0, "Credit Event", ["AAPL"], "2026-01-01T08:00:00+00:00"),  # 8h later, past cooldown
        ]
        decisions = evaluate_signals(signals, threshold=7.0, cooldown_hours=6.0)
        assert decisions[0].fired is True
        assert decisions[1].fired is True

    def test_different_cluster_not_affected_by_cooldown(self):
        signals = [
            _signal("s1", 9.0, "Credit Event", ["AAPL"], "2026-01-01T00:00:00+00:00"),
            _signal("s2", 9.0, "Credit Event", ["MSFT"], "2026-01-01T01:00:00+00:00"),  # different ticker
        ]
        decisions = evaluate_signals(signals, threshold=7.0, cooldown_hours=6.0)
        assert decisions[0].fired is True
        assert decisions[1].fired is True
