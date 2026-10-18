"""Phase 4.3: trigger engine -- threshold filtering and cooldown/dedup."""
from __future__ import annotations

from src.modules.stress_test.trigger import evaluate_signals


def _signal(sig_id, impact, event_class, tickers, created_at, sentiment=-0.5):
    return {
        "signal_id": sig_id,
        "created_at_utc": created_at,
        "impact": {"score": impact},
        "sentiment": {"score": sentiment},
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


class TestSentimentGate:
    """A stress test models losses, so it must only fire on adverse (negative-
    sentiment) signals -- a high-impact signal alone isn't enough. Bug found on
    the real pipeline: Hasbro/Lowe's analyst-upgrade signals (sentiment +0.9x)
    fired the stress test purely on impact score, because Impact Score measures
    how much a story matters, not whether it's good or bad news. See
    ASSUMPTIONS.md "Stress tests only fire on adverse signals"."""

    def test_positive_sentiment_high_impact_does_not_fire(self):
        signals = [_signal("s1", 9.0, "Other", ["HAS"], "2026-01-01T00:00:00+00:00", sentiment=0.942)]
        decisions = evaluate_signals(signals, threshold=7.0)
        assert decisions[0].fired is False
        assert "sentiment" in decisions[0].reason

    def test_zero_sentiment_high_impact_does_not_fire(self):
        signals = [_signal("s1", 9.0, "Other", ["X"], "2026-01-01T00:00:00+00:00", sentiment=0.0)]
        decisions = evaluate_signals(signals, threshold=7.0)
        assert decisions[0].fired is False

    def test_negative_sentiment_high_impact_still_fires(self):
        signals = [_signal("s1", 9.0, "Credit Event", ["AAPL"], "2026-01-01T00:00:00+00:00", sentiment=-0.942)]
        decisions = evaluate_signals(signals, threshold=7.0)
        assert decisions[0].fired is True

    def test_positive_sentiment_below_impact_threshold_reports_impact_not_sentiment(self):
        # impact is checked first -- the reported reason should be about impact,
        # not sentiment, when both would fail it.
        signals = [_signal("s1", 5.0, "Other", ["X"], "2026-01-01T00:00:00+00:00", sentiment=0.9)]
        decisions = evaluate_signals(signals, threshold=7.0)
        assert decisions[0].fired is False
        assert "impact" in decisions[0].reason
