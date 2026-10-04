"""Verifies the README generator's hard guard: it must refuse (raise) rather
than silently write a missing/None metric as if it existed."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from generate_readme import require  # noqa: E402


class TestRequireGuard:
    def test_present_value_returns_it(self):
        assert require({"a": {"b": 5}}, "a", "b") == 5

    def test_missing_key_raises(self):
        with pytest.raises(RuntimeError, match="REFUSING TO GENERATE README"):
            require({"a": {}}, "a", "b")

    def test_none_value_raises(self):
        with pytest.raises(RuntimeError, match="REFUSING TO GENERATE README"):
            require({"a": {"b": None}}, "a", "b")

    def test_pending_metric_block_absent_entirely_raises(self):
        with pytest.raises(RuntimeError):
            require({}, "event_classification_eval", "accuracy")
