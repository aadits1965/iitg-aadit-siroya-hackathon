"""Entity linking: map document text to tickers from the curated universe, or to a
macro/sector/country tag when no company is mentioned.

Design choice (documented, not hidden): linking is done via a curated alias table
(data/universe.csv) plus a small macro-keyword tagger, not full open-domain NER.
For a 20-ticker demo universe this is more precise and fully deterministic/testable
offline than a general NER model, and avoids an extra model download in an
environment where several hosts are already confirmed blocked (see
docs/DATA_VERIFICATION.md section 8). Documented as a scope decision in
docs/ASSUMPTIONS.md, not a silent shortcut.

Precision fixes (review feedback, see docs/DATA_VERIFICATION.md section 11 for
the 50-headline manual audit that found these): a hand-audited sample of 50
real wide-universe-linked headlines came back at ~30% precision before these
fixes, dominated by two bugs:
  1. Bare ticker symbols (e.g. "UPS") were matched case-insensitively as free
     text, so the verb "ups" ("Barclays ups to Overweight") matched United
     Parcel Service. Fixed: ticker symbols are only matched via an explicit
     $CASHTAG pattern (case-sensitive), never as a free-text alias.
  2. The bare word "Target" (alias for Target Corp) matched the extremely
     common financial-news phrase "price target" in >40% of the audited false
     positives. Fixed: AMBIGUOUS_BARE_ALIASES below excludes a handful of
     company names that collide with common English/financial words (also
     covers Visa/Apple/Oracle, flagged in the same review) from free-text
     alias matching -- only the fuller legal name or a cashtag still matches.
A third, smaller pattern -- a sell-side bank's own name appearing only as the
SOURCE of a rating action on a different company ("X downgraded ... at
JPMorgan") rather than as the subject -- is addressed by
_is_analyst_source_mention() below. This heuristic is not perfect (documented
in docs/DATA_VERIFICATION.md section 11 with examples it still misses) but
materially reduces that FP class.
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

# Company names that collide with a common English word or a generic financial
# phrase -- excluded from free-text (case-insensitive) alias matching. Only the
# fuller legal name (company_name, e.g. "Target Corp.") or a $CASHTAG still
# matches. Found via the 50-headline manual audit (docs/DATA_VERIFICATION.md
# section 11); Visa/Target/Apple/Oracle were flagged for review, "Target" was
# confirmed as by far the dominant false-positive source (collides with
# "price target" / "stock price target", ubiquitous in financial headlines).
AMBIGUOUS_BARE_ALIASES = {"target", "visa", "apple", "oracle"}

# Major sell-side banks that frequently appear in financial headlines as the
# SOURCE of a rating action on a different company, not as the subject --
# see _is_analyst_source_mention().
ANALYST_SOURCE_TICKERS = {"JPM", "BAC", "MS", "WFC", "GS", "C"}
_SUBJECT_MARKERS = ("stock", "shares", "share price", "'s stock", "'s shares")
_SOURCE_INDICATORS = (
    "upgrades", "downgrades", "initiates", "initiated", "started at", "starts",
    "raises", "cuts", "says", "sees", "likes", "adds", "ups to", "downs to",
    "target", "bullish", "bearish", "turns", "reels", "gives", "constructive",
    "joins", "out bullish", "out bearish",
)


def _is_analyst_source_mention(text: str, match_start: int, match_end: int) -> bool:
    """True if this occurrence of a bank's name looks like it's naming the bank
    as the analyst/source of a rating action on something else, not as the
    subject of the news itself."""
    right = text[match_end:match_end + 25].lower()
    left = text[max(0, match_start - 10):match_start].lower()

    if any(m in right[:15] for m in _SUBJECT_MARKERS):
        return False  # immediately followed by "stock"/"shares" -> bank IS the subject

    if left.rstrip().endswith(("at", "by")):
        return True  # "... downgraded ... at JPMorgan" / "... upgrade by BofA"

    if any(ind in right[:22] for ind in _SOURCE_INDICATORS):
        return True  # "JPMorgan likes...", "BofA Upgrades...", "Wells Fargo gets bullish...",
        # "JPMorgan reels in...", "Citi gives a boost..."

    return False  # no clear signal either way -- conservative default, keep the match


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
        self._by_ticker = {e.ticker: e for e in self.universe}
        self._cashtag_re = re.compile(r"\$([A-Z]{1,5})\b")
        # Longest alias first so "JPMorgan Chase & Co." matches before a shorter overlapping alias.
        # Bare ticker symbols are deliberately excluded here -- see module docstring -- matched only
        # via the cashtag regex above, and ambiguous common-word aliases are excluded entirely.
        self._patterns: list[tuple[re.Pattern, UniverseEntry]] = []
        for entry in self.universe:
            for alias in sorted(set(entry.aliases), key=len, reverse=True):
                # Case-SENSITIVE comparison deliberately: this excludes a redundant
                # bare-ticker-symbol alias (e.g. "UPS" written verbatim alongside
                # "United Parcel Service", which free-text-matches the common verb
                # "ups"), while still keeping a natural mixed-case company nickname
                # that happens to share the same letters as its ticker (e.g. "Uber"
                # vs ticker "UBER", "Meta" vs ticker "META") -- an UPPERCASE-only
                # alias.upper()==ticker check would wrongly exclude those too (a
                # real bug caught by the 50-headline audit, see module docstring).
                if alias == entry.ticker or alias.lower() in AMBIGUOUS_BARE_ALIASES:
                    continue
                # (?<!\w)...(?!\w) instead of \b on both sides: \b only fires at a
                # word/non-word transition, so it silently fails to anchor after an
                # alias ending in punctuation (e.g. "Target Corp." or "Apple Inc."
                # followed by a space -- "." and " " are both non-word, so there is
                # no transition there and \b never matches). This affects most of
                # this universe's full legal names. Found via the regression test
                # added alongside the audit in docs/DATA_VERIFICATION.md section 11.
                pattern = re.compile(r"(?<!\w)" + re.escape(alias) + r"(?!\w)", re.IGNORECASE)
                self._patterns.append((pattern, entry))

    def link(self, text: str) -> EntityMatch:
        matched_tickers: list[str] = []
        matched_sectors: list[str] = []
        matched_countries: list[str] = []

        for cashtag in self._cashtag_re.findall(text):
            entry = self._by_ticker.get(cashtag)
            if entry and entry.ticker not in matched_tickers:
                matched_tickers.append(entry.ticker)
                matched_sectors.append(entry.sector)
                matched_countries.append(entry.country)

        for pattern, entry in self._patterns:
            if entry.ticker in matched_tickers:
                continue
            m = pattern.search(text)
            if not m:
                continue
            if entry.ticker in ANALYST_SOURCE_TICKERS and _is_analyst_source_mention(text, m.start(), m.end()):
                continue
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
