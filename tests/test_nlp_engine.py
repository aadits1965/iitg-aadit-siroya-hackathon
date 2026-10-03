"""Phase 2 tests for entity linking, impact score maths, event rule classifier,
and the clustering engine — using a fake sentiment scorer so these stay fast and
don't require downloading FinBERT."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.ingestion.schema import Document, SourceType, make_doc_id
from src.nlp.engine import RiskEngine
from src.nlp.entity_linking import EntityLinker
from src.nlp.event_classification import RuleBasedEventClassifier
from src.nlp.impact_score import ImpactScorer
from src.nlp.sentiment import SentimentResult

UTC = timezone.utc


class FakeSentimentScorer:
    """Deterministic stand-in for FinBERT, keyed by substring in the text."""

    def score(self, text: str) -> SentimentResult:
        if "plunge" in text.lower() or "downgrade" in text.lower():
            return SentimentResult(score=-0.8, label="negative", confidence=0.9, model="fake")
        if "soar" in text.lower() or "record" in text.lower():
            return SentimentResult(score=0.8, label="positive", confidence=0.9, model="fake")
        return SentimentResult(score=0.0, label="neutral", confidence=0.5, model="fake")


def _doc(text, dt, source="gdelt", doc_id=None):
    return Document(
        doc_id=doc_id or make_doc_id(source, text),
        source=source,
        source_type=SourceType.NEWS,
        published_at_utc=dt,
        retrieved_at_utc=dt,
        url=f"https://example.com/{abs(hash(text))}",
        title=text,
        text=text,
    )


class TestEntityLinker:
    def test_matches_known_company(self):
        linker = EntityLinker()
        m = linker.link("Tesla shares soar after record deliveries")
        assert "TSLA" in m.tickers
        assert m.sectors == ["Consumer Discretionary"]

    def test_macro_only_gets_market_or_macro_tag(self):
        linker = EntityLinker()
        m = linker.link("Federal Reserve signals further rate hikes amid inflation")
        assert m.tickers == []
        assert "MACRO" in m.macro_tags

    def test_unrelated_text_tagged_market(self):
        linker = EntityLinker()
        m = linker.link("Local bakery wins regional pastry competition")
        assert m.tickers == []
        assert m.macro_tags == ["MARKET"]


class TestImpactScorer:
    def test_weights_sum_to_one(self):
        scorer = ImpactScorer()
        assert abs(sum(scorer.weights.values()) - 1.0) < 1e-6

    def test_score_bounded_1_to_10(self):
        scorer = ImpactScorer()
        lo = scorer.score(sentiment_score=0.0, event_class="Other", num_distinct_sources=0,
                           has_ticker_match=False, is_novel=False)
        hi = scorer.score(sentiment_score=1.0, event_class="Geopolitical", num_distinct_sources=10,
                           has_ticker_match=True, is_novel=True)
        assert 1.0 <= lo.score <= 10.0
        assert 1.0 <= hi.score <= 10.0
        assert hi.score > lo.score

    def test_components_sum_consistently(self):
        scorer = ImpactScorer()
        res = scorer.score(sentiment_score=0.5, event_class="Credit Event", num_distinct_sources=2,
                            has_ticker_match=True, is_novel=True)
        recombined = 1.0 + 9.0 * sum(res.components[k] * scorer.weights[k] for k in res.components)
        assert abs(recombined - res.score) < 0.01


class TestRuleEventClassifier:
    def test_credit_event_detected(self):
        clf = RuleBasedEventClassifier()
        r = clf.classify("Agency downgrades company credit rating amid default risk")
        assert r.event_class == "Credit Event"

    def test_no_keywords_falls_back_to_other(self):
        clf = RuleBasedEventClassifier()
        r = clf.classify("A pleasant walk in the park on a sunny afternoon")
        assert r.event_class == "Other"


class TestRiskEngineClustering:
    def test_multi_source_same_story_clusters_into_one_signal_with_breadth(self):
        t0 = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
        docs = [
            _doc("Tesla stock plunges after recall announcement", t0, source="gdelt", doc_id="a"),
            _doc("Tesla shares plunge amid recall news", t0 + timedelta(minutes=30), source="mastodon", doc_id="b"),
        ]
        engine = RiskEngine(sentiment_scorer=FakeSentimentScorer())
        signals = engine.build_signals(docs)
        assert len(signals) == 1
        sig = signals[0]
        assert sig.tickers == ["TSLA"]
        assert set(sig.sources) == {"gdelt", "mastodon"}
        assert sig.impact.components["source_breadth"] > 0.3  # 2/3 sources, cap=3

    def test_distinct_stories_produce_distinct_signals(self):
        t0 = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
        docs = [
            _doc("Tesla stock plunges after recall announcement", t0, doc_id="a"),
            _doc("Apple shares soar on record iPhone sales", t0, doc_id="b"),
        ]
        engine = RiskEngine(sentiment_scorer=FakeSentimentScorer())
        signals = engine.build_signals(docs)
        assert len(signals) == 2

    def test_repeat_story_within_cooldown_is_not_novel(self):
        t0 = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
        engine = RiskEngine(sentiment_scorer=FakeSentimentScorer())
        first_batch = [_doc("Tesla stock plunges after recall announcement", t0, doc_id="a")]
        # 2h later: same ticker+event cluster, inside the 6h cooldown -> scored as a repeat.
        second_batch = [_doc("Tesla stock plunges again on continued recall fallout", t0 + timedelta(hours=2), doc_id="b")]

        sig1 = engine.build_signals(first_batch)[0]
        sig2 = engine.build_signals(second_batch)[0]
        assert sig1.impact.components["novelty"] == 1.0
        assert sig2.impact.components["novelty"] < 1.0

    def test_repeat_story_outside_cooldown_is_novel_again(self):
        t0 = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
        engine = RiskEngine(sentiment_scorer=FakeSentimentScorer())
        first_batch = [_doc("Tesla stock plunges after recall announcement", t0, doc_id="a")]
        # 8h later: same cluster, but past the 6h cooldown -> treated as novel again.
        second_batch = [_doc("Tesla stock plunges again after second recall", t0 + timedelta(hours=8), doc_id="b")]

        engine.build_signals(first_batch)
        sig2 = engine.build_signals(second_batch)[0]
        assert sig2.impact.components["novelty"] == 1.0
