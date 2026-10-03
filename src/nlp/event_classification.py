"""Event classification: Geopolitical, Macroeconomic, Credit Event,
Merger/Acquisition, Product Launch, Other.

Two methods, both implemented per the brief:
  (a) keyword/rule baseline (fast, transparent, zero model cost)
  (b) zero-shot NLI via facebook/bart-large-mnli (no labelled training data needed)
"""
from __future__ import annotations

import re
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

# "downgrade" is ambiguous: a sell-side equity analyst cutting a stock rating
# ("downgraded to underperform") or trimming a price target is an everyday
# occurrence -- it happens many times a day across thousands of names in a
# retail/social news feed -- and says nothing about an issuer's
# creditworthiness. It must never be classified as a Credit Event on its own.
# Found via real signal output (see docs/DATA_VERIFICATION.md section 12):
# "Disney downgraded as analyst says parks attendance could take 2 years to
# 'normalize'" was wrongly tagged Credit Event at 0.99 confidence purely
# because "downgrade" matched. An initial fix gating on explicit
# analyst-indicator words (e.g. "analyst", "price target") still missed terse
# headlines with no such words, e.g. "Take-Two downgraded on murky game
# slate" -- so the rule below instead requires explicit credit-market
# vocabulary to be PRESENT for "downgrade" to count at all (the inverse
# gate), which is the more conservative default given how heavily
# equity-analyst "downgrade" outnumbers genuine credit-rating downgrades in
# this kind of feed.
CREDIT_MARKET_INDICATORS = [
    "moody's", "moodys", "s&p global ratings", "s&p ratings", "fitch ratings",
    "fitch", "credit rating", "bond rating", "issuer rating", "investment grade",
    "junk status", "junk rating", "notch", "bond", "bonds", "debt rating",
    "notes rating",
]
# Keywords that commonly appear in BOTH a genuine credit event and routine
# equity-analyst commentary -- only "downgrade" is ambiguous enough in
# practice to need this; default/bankruptcy/covenant/restructuring are not
# standard equity-analyst vocabulary.
AMBIGUOUS_CREDIT_KEYWORDS = {"downgrade"}

# Plain substring matching (`kw in lowered`) is dangerous for short keywords:
# "war" matches inside "warns"/"warning"/"forward"/"award" etc. Found via a
# real signal where "<analyst firm> warns on <company>" headlines got
# spuriously tagged Geopolitical (see docs/DATA_VERIFICATION.md section 12 --
# the same root cause also affected src/nlp/entity_linking.py's
# MACRO_KEYWORDS, fixed there identically). Every keyword/indicator phrase
# below is matched with explicit word boundaries instead.
_ALL_KEYWORD_PHRASES = {kw for kws in RULE_KEYWORDS.values() for kw in kws} | set(CREDIT_MARKET_INDICATORS)
_KEYWORD_PATTERNS = {
    phrase: re.compile(r"(?<!\w)" + re.escape(phrase) + r"(?!\w)", re.IGNORECASE) for phrase in _ALL_KEYWORD_PHRASES
}


def _contains(text: str, phrase: str) -> bool:
    return _KEYWORD_PATTERNS[phrase].search(text) is not None


@dataclass
class EventResult:
    event_class: str
    confidence: float
    method: str  # "rule" | "zero_shot"


class RuleBasedEventClassifier:
    method = "rule"

    def classify(self, text: str) -> EventResult:
        has_credit_market_language = any(_contains(text, ind) for ind in CREDIT_MARKET_INDICATORS)

        scores: dict[str, int] = {cls: 0 for cls in RULE_KEYWORDS}
        for cls, keywords in RULE_KEYWORDS.items():
            for kw in keywords:
                if not _contains(text, kw):
                    continue
                if cls == "Credit Event" and kw in AMBIGUOUS_CREDIT_KEYWORDS and not has_credit_market_language:
                    continue  # bare "downgrade" with no credit-market context -- almost always an
                    # equity-analyst stock rating action, not a credit event. See docs/ASSUMPTIONS.md.
                scores[cls] += 1
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
