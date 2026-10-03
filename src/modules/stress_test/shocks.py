"""Loads config/scenarios.yaml and resolves a signal (event_class, impact score,
tickers/sectors/countries) into a concrete ShockSet to apply to the portfolio."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

CONFIG_PATH = Path(__file__).resolve().parents[3] / "config" / "scenarios.yaml"

# Illustrative, documented in docs/ASSUMPTIONS.md: additional spread (bp) a loan/
# bond's rating bucket adds on top of the base risk-free curve, before any shock.
RATING_BASE_SPREAD_BP = {
    "AAA": 30, "AA": 50, "A": 80, "BBB": 150, "BB": 300, "B": 500, "CCC": 900,
}


@dataclass
class ShockSet:
    event_class: str
    tier_name: str
    scope: str  # portfolio_wide | entity_specific
    rate_parallel_bp: float
    equity_pct_move: float
    credit_spread_widening_bp: dict  # {"investment_grade": x, "high_yield": y}
    vix_peak: float
    vix_baseline: float
    pd_multiplier: float
    affected_tickers: set
    affected_sectors: set
    affected_countries: set

    @property
    def vol_multiplier(self) -> float:
        return self.vix_peak / self.vix_baseline

    def credit_spread_bump_bp(self, rating: str) -> float:
        is_hy = rating in ("BB", "B", "CCC")
        return self.credit_spread_widening_bp["high_yield" if is_hy else "investment_grade"]

    def applies_to(self, position_sector: str, position_country: str, position_tickers: set | None = None) -> bool:
        if self.scope == "portfolio_wide":
            return True
        if self.affected_sectors and position_sector in self.affected_sectors:
            return True
        if self.affected_countries and position_country in self.affected_countries:
            return True
        if position_tickers and self.affected_tickers & position_tickers:
            return True
        return False


def load_scenario_config() -> dict:
    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def build_shock_set(
    event_class: str,
    tickers: list[str] | None = None,
    sectors: list[str] | None = None,
    countries: list[str] | None = None,
    config: dict | None = None,
) -> ShockSet:
    cfg = config or load_scenario_config()
    mapping = cfg["event_class_mapping"].get(event_class, cfg["event_class_mapping"]["Other"])
    tier = cfg["severity_tiers"][mapping["tier"]]

    return ShockSet(
        event_class=event_class,
        tier_name=mapping["tier"],
        scope=mapping["scope"],
        rate_parallel_bp=tier["rate_parallel_bp"],
        equity_pct_move=tier["equity_pct_move"],
        credit_spread_widening_bp=tier["credit_spread_widening_bp"],
        vix_peak=tier["vix_peak"],
        vix_baseline=tier["vix_baseline_assumption"],
        pd_multiplier=tier["pd_multiplier"],
        affected_tickers=set(tickers or []),
        affected_sectors=set(sectors or []),
        affected_countries=set(countries or []),
    )
