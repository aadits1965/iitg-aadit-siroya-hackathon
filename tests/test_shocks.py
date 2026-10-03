"""Shock-library tests against the REAL config/scenarios.yaml -- catches config
typos/key mismatches that fixture-based tests elsewhere wouldn't."""
from __future__ import annotations

from src.modules.stress_test.shocks import build_shock_set, load_scenario_config

EXPECTED_EVENT_CLASSES = [
    "Geopolitical", "Macroeconomic", "Credit Event", "Merger/Acquisition", "Product Launch", "Other",
]


class TestRealConfigLoads:
    def test_all_event_classes_resolve_to_a_shock_set(self):
        for event_class in EXPECTED_EVENT_CLASSES:
            shock = build_shock_set(event_class, tickers=["AAPL"], sectors=["Technology"], countries=["US"])
            assert shock.event_class == event_class
            assert shock.narrative  # every tier must have a non-empty one-line narrative
            assert shock.scope in ("portfolio_wide", "entity_specific")

    def test_macro_and_geopolitical_are_portfolio_wide(self):
        assert build_shock_set("Macroeconomic").scope == "portfolio_wide"
        assert build_shock_set("Geopolitical").scope == "portfolio_wide"

    def test_credit_event_is_entity_specific_with_no_rate_move(self):
        """The coherence fix: a single-name credit event must not move the
        broad risk-free curve."""
        shock = build_shock_set("Credit Event")
        assert shock.scope == "entity_specific"
        assert shock.rate_parallel_bp == 0

    def test_fed_scenario_and_brief_scenario_move_rates_in_opposite_directions(self):
        """Coherence check requested in review: the Fed's recessionary
        severely-adverse scenario and the brief's own inflationary example must
        stay distinguishable, not blended into one number."""
        fed = build_shock_set("Macroeconomic")
        geo = build_shock_set("Geopolitical")
        assert fed.rate_parallel_bp < 0  # flight-to-quality: rates fall
        assert geo.rate_parallel_bp > 0  # inflationary shock: rates rise

    def test_vol_multiplier_greater_than_one_for_every_tier(self):
        for event_class in EXPECTED_EVENT_CLASSES:
            shock = build_shock_set(event_class)
            assert shock.vol_multiplier > 1.0, f"{event_class}'s tier has a peak VIX below its own baseline"

    def test_severity_ordering_roughly_matches_impact_prior(self):
        """Sanity check: event classes with a higher event_severity_prior in
        config/impact.yaml should generally map to a tier with a larger equity
        shock -- not a strict proof, just a coherence smell test."""
        macro = build_shock_set("Macroeconomic")
        minor = build_shock_set("Product Launch")
        assert abs(macro.equity_pct_move) > abs(minor.equity_pct_move)


class TestConfigIntegrity:
    def test_every_tier_referenced_by_mapping_exists(self):
        cfg = load_scenario_config()
        tier_names = set(cfg["severity_tiers"])
        for event_class, mapping in cfg["event_class_mapping"].items():
            assert mapping["tier"] in tier_names, f"{event_class} maps to undefined tier {mapping['tier']!r}"

    def test_every_tier_has_required_fields(self):
        cfg = load_scenario_config()
        required = {"narrative", "source", "equity_pct_move", "rate_parallel_bp",
                    "credit_spread_widening_bp", "vix_peak", "vix_baseline", "pd_multiplier"}
        for tier_name, tier in cfg["severity_tiers"].items():
            missing = required - set(tier)
            assert not missing, f"tier {tier_name!r} missing fields: {missing}"
