"""Orchestrates: documents -> per-doc NLP -> clustered signals.

Docs are clustered into "stories" by (affected entities, event class) within a
rolling time window, so that the same story covered by multiple sources produces
one signal with a higher source-breadth component, rather than one signal per
article (Phase 2.6: "every doc -> valid structured signal", read as "every doc
contributes to a signal", since several brief requirements — source breadth,
cooldown/dedup — only make sense at the story level, not the single-article level).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta

from src.ingestion.schema import Document
from src.nlp.entity_linking import EntityLinker, EntityMatch
from src.nlp.event_classification import EventResult, RuleBasedEventClassifier
from src.nlp.impact_score import ImpactScorer
from src.nlp.sentiment import SentimentResult
from src.signals.schema import EventBlock, ImpactBlock, Signal, SentimentBlock, make_signal_id

CLUSTER_WINDOW = timedelta(hours=6)
COOLDOWN = timedelta(hours=6)


@dataclass
class DocAnalysis:
    doc: Document
    entities: EntityMatch
    sentiment: SentimentResult
    event: EventResult


class RiskEngine:
    def __init__(
        self,
        sentiment_scorer,
        event_classifier=None,
        entity_linker: EntityLinker | None = None,
        impact_scorer: ImpactScorer | None = None,
    ):
        self.sentiment_scorer = sentiment_scorer
        self.event_classifier = event_classifier or RuleBasedEventClassifier()
        self.entity_linker = entity_linker or EntityLinker()
        self.impact_scorer = impact_scorer or ImpactScorer()
        self._last_seen_cluster: dict[tuple, object] = {}  # cluster_key -> last created_at_utc

    def analyze_doc(self, doc: Document) -> DocAnalysis:
        entities = self.entity_linker.link(doc.text)
        sentiment = self.sentiment_scorer.score(doc.text)
        event = self.event_classifier.classify(doc.text)
        return DocAnalysis(doc=doc, entities=entities, sentiment=sentiment, event=event)

    @staticmethod
    def _cluster_key(analysis: DocAnalysis) -> tuple:
        entity_key = tuple(sorted(analysis.entities.tickers)) or tuple(sorted(analysis.entities.macro_tags))
        return (entity_key, analysis.event.event_class)

    def build_signals(self, docs: list[Document]) -> list[Signal]:
        analyses = [self.analyze_doc(d) for d in docs]
        analyses.sort(key=lambda a: a.doc.published_at_utc)

        clusters: dict[tuple, list[DocAnalysis]] = {}
        for a in analyses:
            key = self._cluster_key(a)
            bucket = clusters.setdefault(key, [])
            if bucket and (a.doc.published_at_utc - bucket[-1].doc.published_at_utc) > CLUSTER_WINDOW:
                # window elapsed for this key; start a fresh cluster under a disambiguated key
                key = key + (a.doc.published_at_utc.isoformat(),)
                bucket = clusters.setdefault(key, [])
            bucket.append(a)

        signals: list[Signal] = []
        for key, bucket in clusters.items():
            signals.append(self._build_signal(key, bucket))
        return signals

    def _build_signal(self, cluster_key: tuple, bucket: list[DocAnalysis]) -> Signal:
        latest = bucket[-1]
        doc_ids = [a.doc.doc_id for a in bucket]
        sources = sorted({a.doc.source for a in bucket})
        tickers = sorted({t for a in bucket for t in a.entities.tickers})
        sectors = sorted({s for a in bucket for s in a.entities.sectors})
        countries = sorted({c for a in bucket for c in a.entities.countries})
        macro_tags = sorted({m for a in bucket for m in a.entities.macro_tags})

        # Representative sentiment = the most extreme |score| in the cluster (the
        # most alarming/bullish single report), not a mean that could wash out a
        # genuinely sharp signal buried among neutral wire reprints.
        rep_sentiment_doc = max(bucket, key=lambda a: abs(a.sentiment.score))
        sentiment = rep_sentiment_doc.sentiment

        event_class = latest.event.event_class
        event_confidence = latest.event.confidence

        key_prefix = cluster_key[:2]
        prior_seen = self._last_seen_cluster.get(key_prefix)
        is_novel = prior_seen is None or (latest.doc.published_at_utc - prior_seen) > COOLDOWN
        self._last_seen_cluster[key_prefix] = latest.doc.published_at_utc

        impact = self.impact_scorer.score(
            sentiment_score=sentiment.score,
            event_class=event_class,
            num_distinct_sources=len(sources),
            has_ticker_match=bool(tickers),
            is_novel=is_novel,
        )

        return Signal(
            signal_id=make_signal_id(doc_ids),
            # Derived from the cluster's own latest document timestamp, NOT
            # wall-clock now() -- a signal's time should reflect when its
            # underlying evidence was published, not when a particular batch
            # job happened to run. This also makes demo mode deterministic:
            # the same cached docs always produce byte-identical signals.jsonl
            # across runs (see tests/test_demo_idempotency.py), which calling
            # now() here would make impossible by construction.
            created_at_utc=latest.doc.published_at_utc,
            doc_ids=doc_ids,
            sources=sources,
            tickers=tickers,
            sectors=sectors,
            countries=countries,
            macro_tags=macro_tags,
            sentiment=SentimentBlock(**sentiment.__dict__),
            event=EventBlock(event_class=event_class, confidence=event_confidence, method=latest.event.method),
            impact=ImpactBlock(score=impact.score, components=impact.components),
            model_versions={
                "sentiment_model": sentiment.model,
                "event_method": latest.event.method,
                "event_classifier_version": getattr(self.event_classifier, "version", "unknown"),
            },
            text_preview=(latest.doc.title or latest.doc.text)[:200],
        )
