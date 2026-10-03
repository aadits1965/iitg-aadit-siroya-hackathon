"""Phase 4: synthetic portfolio generator -- deterministic, asset-class mix,
no real counterparty names, round-trip save/load."""
from __future__ import annotations

from src.modules.stress_test.portfolio import (
    FICTIONAL_PREFIXES,
    generate_portfolio,
    load_portfolio,
    save_portfolio,
)

REAL_NAME_BLOCKLIST = ["S&P Global", "Crisil", "CRISIL", "Moody's", "Fitch"]  # must never appear as counterparties


class TestPortfolioGeneration:
    def test_deterministic_with_fixed_seed(self):
        p1 = generate_portfolio(n_positions=50, seed=1234)
        p2 = generate_portfolio(n_positions=50, seed=1234)
        assert [p.position_id for p in p1] == [p.position_id for p in p2]
        assert [p.notional for p in p1] == [p.notional for p in p2]

    def test_different_seed_differs(self):
        p1 = generate_portfolio(n_positions=50, seed=1234)
        p2 = generate_portfolio(n_positions=50, seed=9999)
        assert [p.notional for p in p1] != [p.notional for p in p2]

    def test_asset_class_mix_present(self):
        positions = generate_portfolio(n_positions=50, seed=1234)
        classes = {p.asset_class for p in positions}
        assert "loan" in classes
        assert "bond" in classes
        assert classes & {"swap", "option", "fx_forward"}  # at least one derivative type

    def test_counterparty_names_are_fictional(self):
        positions = generate_portfolio(n_positions=50, seed=1234)
        for p in positions:
            if p.counterparty == "US Treasury":
                continue  # sovereign bonds legitimately reference the real issuer
            assert any(prefix in p.counterparty for prefix in FICTIONAL_PREFIXES)
            for blocked in REAL_NAME_BLOCKLIST:
                assert blocked not in p.counterparty

    def test_all_pds_and_lgds_in_unit_interval(self):
        positions = generate_portfolio(n_positions=50, seed=1234)
        for p in positions:
            assert 0.0 < p.pd < 1.0
            assert 0.0 < p.lgd < 1.0

    def test_notionals_positive(self):
        positions = generate_portfolio(n_positions=50, seed=1234)
        assert all(p.notional > 0 for p in positions)


class TestPortfolioRoundTrip:
    def test_save_and_load_preserves_data(self, tmp_path):
        positions = generate_portfolio(n_positions=20, seed=1234)
        path = tmp_path / "portfolio.csv"
        save_portfolio(positions, path=path)
        loaded = load_portfolio(path=path)

        assert len(loaded) == len(positions)
        for orig, got in zip(positions, loaded):
            assert orig.position_id == got.position_id
            assert orig.asset_class == got.asset_class
            assert orig.notional == got.notional
            assert orig.extra == got.extra
