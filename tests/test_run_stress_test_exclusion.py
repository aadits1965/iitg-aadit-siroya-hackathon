"""Equity spot prices are only needed to price `option` positions (Black-
Scholes strike/quantity) -- loans/bonds/swaps/FX never touch them. If a real
spot price is unavailable (e.g. yfinance down), exclude_unpriceable_options()
must drop just the affected option position(s), loudly, rather than crashing
the whole stress test (which is what the raw revaluation code does, by
design, if called directly with a missing spot)."""
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from run_stress_test import exclude_unpriceable_options  # noqa: E402


@dataclass
class _Pos:
    position_id: str
    asset_class: str
    notional: float = 1_000_000.0
    extra: dict = field(default_factory=dict)


def _loan(pid="L1"):
    return _Pos(pid, "loan")


def _option(pid, underlying):
    return _Pos(pid, "option", extra={"underlying": underlying})


class TestExcludeUnpriceableOptions:
    def test_no_options_passes_through_unchanged(self):
        portfolio = [_loan("L1"), _loan("L2")]
        priceable, excluded = exclude_unpriceable_options(portfolio, equity_spot={})
        assert priceable == portfolio
        assert excluded == []

    def test_option_with_spot_price_available_is_kept(self):
        portfolio = [_option("D1", "JPM")]
        priceable, excluded = exclude_unpriceable_options(portfolio, equity_spot={"JPM": 250.0})
        assert priceable == portfolio
        assert excluded == []

    def test_option_missing_spot_price_is_excluded_and_reported(self):
        portfolio = [_loan("L1"), _option("D1", "JPM")]
        priceable, excluded = exclude_unpriceable_options(portfolio, equity_spot={})
        assert priceable == [portfolio[0]]
        assert len(excluded) == 1
        assert excluded[0]["position_id"] == "D1"
        assert excluded[0]["underlying"] == "JPM"
        assert "JPM" in excluded[0]["reason"]

    def test_only_affected_underlying_is_excluded_others_kept(self):
        portfolio = [_option("D1", "JPM"), _option("D2", "NVDA")]
        priceable, excluded = exclude_unpriceable_options(portfolio, equity_spot={"NVDA": 180.0})
        assert priceable == [portfolio[1]]
        assert [e["position_id"] for e in excluded] == ["D1"]

    def test_all_options_missing_leaves_only_non_option_positions(self):
        portfolio = [_loan("L1"), _option("D1", "JPM"), _option("D2", "NVDA")]
        priceable, excluded = exclude_unpriceable_options(portfolio, equity_spot={})
        assert priceable == [portfolio[0]]
        assert len(excluded) == 2
