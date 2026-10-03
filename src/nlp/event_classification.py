"""Event classification: Geopolitical, Macroeconomic, Credit Event,
Merger/Acquisition, Product Launch, Other.

Two methods, both implemented per the brief:
  (a) keyword/rule baseline (fast, transparent, zero model cost)
  (b) zero-shot NLI via facebook/bart-large-mnli (no labelled training data needed)
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

EVENT_CLASSES = [
    "Geopolitical",
    "Macroeconomic",
    "Credit Event",
    "Merger/Acquisition",
    "Product Launch",
    "Other",
]

ZERO_SHOT_MODEL_NAME = "facebook/bart-large-mnli"

RULE_KEYWORDS: dict[str, list[str]] = {
    "Geopolitical": ["sanctions", "war", "invasion", "tariff", "trade war", "geopolitical", "conflict"],
    "Macroeconomic": [
        "federal reserve", "interest rate", "inflation", "gdp", "unemployment",
        "recession", "treasury yield", "central bank", "rate hike", "rate cut",
    ],
    "Credit Event": ["downgrade", "default", "bankruptcy", "credit rating", "covenant", "restructuring"],
    "Merger/Acquisition": ["merger", "acquisition", "acquire", "takeover", "buyout", "deal to buy"],
    "Product Launch": ["launches", "unveils", "announces new", "new product", "release of"],
}


@dataclass
class EventResult:
    event_class: str
    confidence: float
    method: str  # "rule" | "zero_shot"


class RuleBasedEventClassifier:
    method = "rule"

    def classify(self, text: str) -> EventResult:
        lowered = text.lower()
        scores: dict[str, int] = {cls: 0 for cls in RULE_KEYWORDS}
        for cls, keywords in RULE_KEYWORDS.items():
            scores[cls] = sum(1 for kw in keywords if kw in lowered)
        best_cls = max(scores, key=scores.get)
        best_hits = scores[best_cls]
        if best_hits == 0:
            return EventResult(event_class="Other", confidence=0.34, method=self.method)
        total_hits = sum(scores.values()) or 1
        confidence = min(0.5 + 0.5 * (best_hits / total_hits), 0.99)
        return EventResult(event_class=best_cls, confidence=confidence, method=self.method)


@lru_cache(maxsize=1)
def _load_zero_shot_pipeline():
    from transformers import pipeline

    return pipeline("zero-shot-classification", model=ZERO_SHOT_MODEL_NAME)


class ZeroShotEventClassifier:
    method = "zero_shot"
    model_name = ZERO_SHOT_MODEL_NAME

    def classify(self, text: str) -> EventResult:
        clf = _load_zero_shot_pipeline()
        result = clf(text, candidate_labels=EVENT_CLASSES, multi_label=False)
        return EventResult(
            event_class=result["labels"][0],
            confidence=float(result["scores"][0]),
            method=self.method,
        )
