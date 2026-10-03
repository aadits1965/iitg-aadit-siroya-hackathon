"""Sentiment scoring: -1..1. Primary = FinBERT (ProsusAI/finbert), P(pos) - P(neg).
Baseline = VADER lexicon (for the required "vs naive approach" comparison).

CAUTION (see docs/DATA_VERIFICATION.md): FinBERT was fine-tuned on Financial
PhraseBank. Never evaluate accuracy on PhraseBank or its Kaggle mirror — Phase 3
evaluation uses a disjoint dataset instead.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Protocol

MODEL_NAME = "ProsusAI/finbert"


@dataclass
class SentimentResult:
    score: float  # -1..1
    label: str  # positive|negative|neutral
    confidence: float
    model: str


class SentimentScorer(Protocol):
    def score(self, text: str) -> SentimentResult: ...


@lru_cache(maxsize=1)
def _load_finbert():
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    model = AutoModelForSequenceClassification.from_pretrained(MODEL_NAME)
    model.eval()
    return tokenizer, model


class FinBertSentimentScorer:
    """Lazy-loads the model on first .score() call (first run downloads weights —
    documented in README as a one-time cost)."""

    model_name = MODEL_NAME

    def score(self, text: str) -> SentimentResult:
        import torch

        tokenizer, model = _load_finbert()
        inputs = tokenizer(text, return_tensors="pt", truncation=True, max_length=512)
        with torch.no_grad():
            logits = model(**inputs).logits
        probs = torch.softmax(logits, dim=-1)[0].tolist()
        # Read the label order from the model's own config rather than hardcoding it,
        # since label-index order varies by checkpoint and must not be assumed.
        id2label = model.config.id2label
        prob_by_label = {id2label[i].lower(): p for i, p in enumerate(probs)}
        pos = prob_by_label.get("positive", 0.0)
        neg = prob_by_label.get("negative", 0.0)
        score = pos - neg
        label = max(prob_by_label, key=prob_by_label.get)
        confidence = prob_by_label[label]
        return SentimentResult(score=score, label=label, confidence=confidence, model=self.model_name)


class VaderSentimentScorer:
    """Naive lexicon baseline used for the required engine-vs-baseline comparison."""

    model_name = "vader"

    def __init__(self):
        from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

        self._analyzer = SentimentIntensityAnalyzer()

    def score(self, text: str) -> SentimentResult:
        scores = self._analyzer.polarity_scores(text)
        compound = scores["compound"]  # already -1..1
        if compound >= 0.05:
            label = "positive"
        elif compound <= -0.05:
            label = "negative"
        else:
            label = "neutral"
        confidence = max(scores["pos"], scores["neg"], scores["neu"])
        return SentimentResult(score=compound, label=label, confidence=confidence, model=self.model_name)
