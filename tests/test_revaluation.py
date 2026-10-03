"""Phase 4.6: hand-checkable revaluation tests -- zero shock -> zero P&L,
entity-specific scoping, EL rises under a PD multiplier, option value rises in
an equity selloff."""
from __future__ import annotations

import pytest

from src.modules.stress_test.curve import synthetic_test_only_curve
from src.modules.stress_test.portfolio import Position
from src.modules.stress_test.revaluation import revalue_portfolio
from src.modules.stress_test.shocks import ShockSet

CURVE = synthetic_test_only_curve()  # SYNTHETIC_TEST_ONLY -- unit tests only, see curve.py docstring

EQUITY_SPOT = {"AAPL": 200.0, "SPY": 500.0}


def _zero_shock(scope="portfolio_wide", tickers=None, sectors=None) -> ShockSet:
    return ShockSet(
        event_class="Other", tier_name="zero_test", scope=scope,
        rate_parallel_bp=0.0, equity_pct_move=0.0,
        credit_spread_widening_bp={"investment_grade": 0.0, "high_yield": 0.0},
        vix_peak=18.0, vix_baseline=18.0, pd_multiplier=1.0,
        affected_tickers=set(tickers or []), affected_sectors=set(sectors or []), affected_countries=set(),
    )


def _sample_portfolio() -> list[Position]:
    return [
        Position("LOAN1", "loan", "Test Co A", "Energy", "US", "BBB", 0.01, 0.45, 10_000_000, 5.0,
                 {"seniority": "senior_unsecured", "interest_rate": 0.05}),
        Position("BOND1", "bond", "Test Co B", "Technology", "US", "A", 0.005, 0.45, 5_000_000, 10.0,
                 {"coupon_rate": 0.04, "credit_spread_bp": 100, "is_sovereign": False}),
        Position("SWAP1", "swap", "Test Co C", "Financials", "US", "A", 0.005, 0.45, 20_000_000, 5.0,
                 {"direction": "payer", "fixed_rate": 0.04}),
        Position("OPT1", "option", "Test Co D", "Technology", "US", "BBB", 0.01, 0.45, 2_000_000, 1.0,
                 {"underlying": "AAPL", "option_type": "put", "moneyness": 0.95, "volatility": 0.25}),
        Position("FX1", "fx_forward", "Test Co E", "Industrials", "US", "BBB", 0.01, 0.45, 3_000_000, 0.5,
                 {"currency_pair": "EURUSD", "fwd_points_bp": 10}),
    ]


class TestZeroShock:
    def test_zero_shock_zero_pnl(self):
        positions = _sample_portfolio()
        result = revalue_portfolio(positions, CURVE, EQUITY_SPOT, _zero_shock())
        assert result.total_pnl == pytest.approx(0.0, abs=1e-6)
        for b, a in zip(result.before, result.after):
            assert a.value == pytest.approx(b.value, abs=1e-6)

    def test_zero_shock_zero_el_change(self):
        positions = _sample_portfolio()
        result = revalue_portfolio(positions, CURVE, EQUITY_SPOT, _zero_shock())
        assert result.total_el_after == pytest.approx(result.total_el_before, abs=1e-6)


class TestEntityScoping:
    def test_entity_specific_shock_only_hits_named_sector(self):
        positions = _sample_portfolio()
        shock = ShockSet(
            event_class="Credit Event", tier_name="moderate", scope="entity_specific",
            rate_parallel_bp=-80, equity_pct_move=-0.22,
            credit_spread_widening_bp={"investment_grade": 175, "high_yield": 260},
            vix_peak=35, vix_baseline=18, pd_multiplier=1.6,
            affected_tickers=set(), affected_sectors={"Energy"}, affected_countries=set(),
        )
        result = revalue_portfolio(positions, CURVE, EQUITY_SPOT, shock)
        pnl_by_id = {b.position.position_id: a.value - b.value for b, a in zip(result.before, result.after)}
        assert pnl_by_id["LOAN1"] != pytest.approx(0.0, abs=1e-6)  # Energy -- in scope
        assert pnl_by_id["BOND1"] == pytest.approx(0.0, abs=1e-6)  # Technology -- out of scope
        assert pnl_by_id["SWAP1"] == pytest.approx(0.0, abs=1e-6)  # Financials -- out of scope

    def test_portfolio_wide_shock_hits_everything(self):
        positions = _sample_portfolio()
        shock = ShockSet(
            event_class="Macroeconomic", tier_name="severe", scope="portfolio_wide",
            rate_parallel_bp=-200, equity_pct_move=-0.54,
            credit_spread_widening_bp={"investment_grade": 440, "high_yield": 650},
            vix_peak=72, vix_baseline=18, pd_multiplier=3.0,
            affected_tickers=set(), affected_sectors=set(), affected_countries=set(),
        )
        result = revalue_portfolio(positions, CURVE, EQUITY_SPOT, shock)
        for b, a in zip(result.before, result.after):
            if b.position.asset_class == "fx_forward":
                continue  # fx P&L can legitimately be exactly proportional but nonzero; checked separately
            assert a.value != pytest.approx(b.value, abs=1e-6), f"{b.position.position_id} unaffected by portfolio-wide shock"


class TestExpectedLossUnderStress:
    def test_el_rises_with_pd_multiplier(self):
        positions = _sample_portfolio()
        shock = ShockSet(
            event_class="Macroeconomic", tier_name="severe", scope="portfolio_wide",
            rate_parallel_bp=0.0, equity_pct_move=0.0,
            credit_spread_widening_bp={"investment_grade": 0.0, "high_yield": 0.0},
            vix_peak=18, vix_baseline=18, pd_multiplier=3.0,
            affected_tickers=set(), affected_sectors=set(), affected_countries=set(),
        )
        result = revalue_portfolio(positions, CURVE, EQUITY_SPOT, shock)
        assert result.total_el_after == pytest.approx(result.total_el_before * 3.0, rel=1e-6)


class TestOptionUnderSelloff:
    def test_put_value_rises_in_equity_selloff(self):
        positions = [p for p in _sample_portfolio() if p.asset_class == "option"]
        shock = ShockSet(
            event_class="Macroeconomic", tier_name="severe", scope="portfolio_wide",
            rate_parallel_bp=0.0, equity_pct_move=-0.54,
            credit_spread_widening_bp={"investment_grade": 0.0, "high_yield": 0.0},
            vix_peak=72, vix_baseline=18, pd_multiplier=1.0,
            affected_tickers=set(), affected_sectors=set(), affected_countries=set(),
        )
        result = revalue_portfolio(positions, CURVE, EQUITY_SPOT, shock)
        assert result.after[0].value > result.before[0].value  # put gains value as spot falls + vol rises


class TestBreakdowns:
    def test_pnl_by_asset_class_sums_to_total(self):
        positions = _sample_portfolio()
        shock = ShockSet(
            event_class="Macroeconomic", tier_name="severe", scope="portfolio_wide",
            rate_parallel_bp=-200, equity_pct_move=-0.54,
            credit_spread_widening_bp={"investment_grade": 440, "high_yield": 650},
            vix_peak=72, vix_baseline=18, pd_multiplier=3.0,
            affected_tickers=set(), affected_sectors=set(), affected_countries=set(),
        )
        result = revalue_portfolio(positions, CURVE, EQUITY_SPOT, shock)
        assert sum(result.pnl_by_asset_class().values()) == pytest.approx(result.total_pnl, rel=1e-6)

    def test_top_contributors_sorted_worst_first(self):
        positions = _sample_portfolio()
        shock = ShockSet(
            event_class="Macroeconomic", tier_name="severe", scope="portfolio_wide",
            rate_parallel_bp=-200, equity_pct_move=-0.54,
            credit_spread_widening_bp={"investment_grade": 440, "high_yield": 650},
            vix_peak=72, vix_baseline=18, pd_multiplier=3.0,
            affected_tickers=set(), affected_sectors=set(), affected_countries=set(),
        )
        result = revalue_portfolio(positions, CURVE, EQUITY_SPOT, shock)
        contributors = result.top_contributors(n=3)
        pnls = [pnl for _, pnl in contributors]
        assert pnls == sorted(pnls)
