"""Regression tests for the precision bugs found by the 50-headline manual
audit (docs/DATA_VERIFICATION.md section 11): these are real headline patterns
that were false positives before the fix, pinned here so they can't silently
come back. See src/nlp/entity_linking.py module docstring for the full story."""
from __future__ import annotations

from pathlib import Path

from src.nlp.entity_linking import EntityLinker, load_universe

WIDE_UNIVERSE = load_universe(Path("data/universe_event_study.csv"))


def linker() -> EntityLinker:
    return EntityLinker(universe=WIDE_UNIVERSE)


class TestAmbiguousBareAliasesExcluded:
    def test_price_target_phrase_does_not_match_target_corp(self):
        m = linker().link("Ligand Pharmaceuticals started at buy with $135 stock price target at Benchmark")
        assert "TGT" not in m.tickers

    def test_fed_target_does_not_match_target_corp(self):
        m = linker().link("inflation remained above the Fed's target throughout the quarter")
        assert "TGT" not in m.tickers

    def test_different_company_sharing_the_word_target_not_confused(self):
        """'Target Hospitality' is a real, different company -- must not be
        silently attributed to Target Corp."""
        m = linker().link("Target Hospitality downgraded to perform from outperform at Oppenheimer")
        assert "TGT" not in m.tickers

    def test_full_legal_name_still_matches_target_corp(self):
        m = linker().link("Target Corp. reported quarterly earnings above expectations")
        assert "TGT" in m.tickers

    def test_bare_apple_matches(self):
        """Apple/Oracle were removed from the exclusion set after a recall
        check found zero false-positive benefit for either across the full
        corpus (6/6 bare occurrences were genuine company mentions) -- see
        docs/DATA_VERIFICATION.md section 13."""
        m = linker().link("Apple closing all China stores and offices")
        assert "AAPL" in m.tickers

    def test_bare_oracle_matches(self):
        m = linker().link("Oracle's Need for 'Steep' Sales Climb Leaves Street Cautious")
        assert "ORCL" in m.tickers


class TestBareTickerVerbCollisionExcluded:
    def test_ups_verb_does_not_match_united_parcel_service(self):
        m = linker().link("Barclays ups $JD to Overweight")
        assert "UPS" not in m.tickers

    def test_cashtag_still_matches_ups(self):
        m = linker().link("$UPS reported strong delivery volumes this quarter")
        assert "UPS" in m.tickers


class TestCompanyNicknameEqualToTickerStillMatches:
    """Regression guard for a bug introduced by the first fix attempt: a
    case-insensitive alias==ticker check wrongly excluded legitimate natural
    mentions like "Uber" (ticker UBER) and "Meta" (ticker META)."""

    def test_uber_bare_mention_matches(self):
        m = linker().link("Barclays analysts say Uber and Lyft are well-positioned to achieve profitability")
        assert "UBER" in m.tickers

    def test_meta_bare_mention_matches(self):
        m = linker().link("Alphabet and Facebook price targets cut at Barclays on weaker ad outlook")
        # (Meta Platforms Inc.'s aliases include "Facebook", a real historical/
        # common name for the company -- not the bare word "Meta" test case,
        # but exercises the same company-name-alias path.)
        assert "META" in m.tickers


class TestAnalystSourceMentionSuppressed:
    def test_bank_named_as_source_of_rating_action_is_suppressed(self):
        """'Autodesk downgraded ... at JPMorgan' -- JPMorgan is the source,
        Autodesk (not in our universe) is the subject. JPM must not be
        attributed as an affected entity."""
        m = linker().link("Autodesk downgraded to underweight from neutral at JPMorgan")
        assert "JPM" not in m.tickers

    def test_bank_as_genuine_subject_still_matches(self):
        m = linker().link("Bank of America stock price target raised to $49 from $48 at Oppenheimer")
        assert "BAC" in m.tickers

    def test_bank_upgrades_another_company_suppressed(self):
        m = linker().link("BofA Upgrades WestRock After Containerboard Conference")
        assert "BAC" not in m.tickers

    def test_bank_turns_bullish_on_another_company_suppressed(self):
        m = linker().link("Nvidia stock climbs after Morgan Stanley turns bullish")
        assert "MS" not in m.tickers
        assert "NVDA" in m.tickers
