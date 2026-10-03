"""Entity linking: map document text to tickers from the curated universe, or to a
macro/sector/country tag when no company is mentioned.

Design choice (documented, not hidden): linking is done via a curated alias table
(data/universe.csv) plus a small macro-keyword tagger, not full open-domain NER.
For a 20-ticker demo universe this is more precise and fully deterministic/testable
offline than a general NER model, and avoids an extra model download in an
environment where several hosts are already confirmed blocked (see
docs/DATA_VERIFICATION.md section 8). Documented as a scope decision in
docs/ASSUMPTIONS.md, not a silent shortcut.
"""
from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path

UNIVERSE_PATH = Path(__file__).resolve().parents[2] / "data" / "universe.csv"

MACRO_KEYWORDS = {
    "federal reserve": ("MACRO", "US"),
    "interest rate": ("MACRO", None),
    "treasury yield": ("MACRO", "US"),
    "inflation": ("MACRO", None),
    "recession": ("MACRO", None),
    "sanctions": ("GEOPOLITICAL", None),
    "geopolitical": ("GEOPOLITICAL", None),
    "war": ("GEOPOLITICAL", None),
    "credit rating": ("CREDIT", None),
    "downgrade": ("CREDIT", None),
    "default": ("CREDIT", None),
    "china": ("GEOPOLITICAL", "CN"),
    "opec": ("MACRO", None),
}


@dataclass(frozen=True)
class UniverseEntry:
    ticker: str
    company_name: str
    aliases: tuple[str, ...]
    sector: str
    country: str


def load_universe(path: Path = UNIVERSE_PATH) -> list[UniverseEntry]:
    entries = []
    with path.open("r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            aliases = tuple(a.strip() for a in row["aliases"].split("|") if a.strip())
            entries.append(
                UniverseEntry(
                    ticker=row["ticker"],
                    company_name=row["company_name"],
                    aliases=(row["company_name"],) + aliases,
                    sector=row["sector"],
                    country=row["country"],
                )
            )
    return entries


@dataclass
class EntityMatch:
    tickers: list[str]
    sectors: list[str]
    macro_tags: list[str]  # e.g. "MACRO", "GEOPOLITICAL", "CREDIT"
    countries: list[str]


class EntityLinker:
    def __init__(self, universe: list[UniverseEntry] | None = None):
        self.universe = universe or load_universe()
        # Longest alias first so "JPMorgan Chase & Co." matches before a shorter overlapping alias.
        self._patterns: list[tuple[re.Pattern, UniverseEntry]] = []
        for entry in self.universe:
            for alias in sorted(set(entry.aliases), key=len, reverse=True):
                pattern = re.compile(r"\b" + re.escape(alias) + r"\b", re.IGNORECASE)
                self._patterns.append((pattern, entry))

    def link(self, text: str) -> EntityMatch:
        matched_tickers: list[str] = []
        matched_sectors: list[str] = []
        matched_countries: list[str] = []
        for pattern, entry in self._patterns:
            if pattern.search(text) and entry.ticker not in matched_tickers:
                matched_tickers.append(entry.ticker)
                matched_sectors.append(entry.sector)
                matched_countries.append(entry.country)

        macro_tags: list[str] = []
        lowered = text.lower()
        for kw, (tag, country) in MACRO_KEYWORDS.items():
            if kw in lowered:
                if tag not in macro_tags:
                    macro_tags.append(tag)
                if country and country not in matched_countries:
                    matched_countries.append(country)

        if not matched_tickers and not macro_tags:
            macro_tags.append("MARKET")

        return EntityMatch(
            tickers=matched_tickers,
            sectors=sorted(set(matched_sectors)),
            macro_tags=macro_tags,
            countries=sorted(set(matched_countries)),
        )
