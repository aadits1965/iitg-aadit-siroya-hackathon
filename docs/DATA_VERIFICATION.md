# Data Source Verification

Verified 2026-10-04 by actually querying/reading each source's docs (not assumed). Each entry is labeled
FACT (directly observed from the source), ASSUMPTION (stated by the source but not independently tested),
or JUDGMENT (a call made based on the facts).

## 1. GDELT DOC 2.0 API — primary NEWS source

- FACT: Base URL `https://api.gdeltproject.org/api/v2/doc/doc`. No API key required.
- FACT: `QUERY` supports keywords, exact phrases, boolean OR, `domain:`, `sourcelang:`, `sourcecountry:`,
  `theme:` (GDELT GKG themes), `tone:`/`toneabs:`.
- FACT: `TIMESPAN` default 3 months; can set explicit `STARTDATETIME`/`ENDDATETIME` (`YYYYMMDDHHMMSS`).
- FACT: `MAXRECORDS` default 75, max 250 per request in ArtList/JSON mode. Output formats: JSON, JSONP, CSV, RSS.
- FACT: Rolling 3-month search window only (no deep historical archive via this endpoint — the separate GKG
  files on Google BigQuery/AWS would be needed for history beyond 3 months; out of scope for this project).
- ASSUMPTION: no documented hard rate limit on the live DOC API. JUDGMENT: self-throttle to ~1 request per
  3–5 seconds and cache every response to `data/cache/` so the demo never depends on live GDELT availability.
- FACT: GDELT Project data is released **CC0 (public domain)**; redistribution/rehosting is explicitly permitted,
  conditional only on citing the GDELT Project and linking gdeltproject.org. Safe to cache a small sample in
  `/data` with that citation.
- **Decision:** GDELT DOC 2.0 is the primary news adapter, `replay` mode built from a cached snapshot.

## 2. NewsAPI.org — optional secondary NEWS source

- FACT: Free "Developer" plan = 100 requests/day, articles delayed ~24h, search window capped at ~1 month back.
- FACT: Developer-plan ToS restricts use to **development and testing**, not production/published/commercial
  deployment; CORS only from localhost.
- JUDGMENT: a hackathon prototype that is never deployed as a live production service is consistent with
  "development and testing." Still, to avoid any ambiguity and avoid a submission-time dependency on a 100
  req/day quota, NewsAPI is wired as an **optional, clearly-labeled secondary adapter for `--live` mode only**.
  The required `--demo` replay path never calls it. This keeps the graded demo compliant regardless of how
  that clause is read.

## 3. "Social" source — X/Twitter API is NOT viable free in 2026

- FACT (verified via search of current 2026 pricing pages): X retired its free read tier. The current free
  tier is **write-only** (1,500 posts/month) with **zero read access** beyond `GET /2/users/me`. Reading posts
  is pay-per-use (~$0.005/read); full-archive search requires an Enterprise contract (~$42,000/month).
- JUDGMENT: a live X feed is not viable for this project, exactly as flagged as a risk in the brief. Confirms
  the plan's own warning.
- **Decision:** use **`zeroshot/twitter-financial-news-sentiment`** (Hugging Face) as the social-source adapter,
  replayed as a stream rather than pulled live.
  - FACT: MIT licensed. 11,932 labeled finance tweets, 3-class (Bearish/Bullish/Neutral), split
    train=9,938 / validation=2,486.
  - JUDGMENT: MIT license permits redistributing a small sample in this public repo with attribution — a
    capped sample (a few hundred rows) goes in `data/raw_samples/`, with a link to the source dataset.
  - **This is a static replay, not a live feed.** The README, deck, and `QA_PREP.md` will say this plainly —
    it satisfies "ingest from ≥2 distinct source *types*" (news vs. social) honestly, but social ingestion is
    not real-time in this build. Logged as a stated limitation, not hidden.

## 4. FinBERT (`ProsusAI/finbert`) — confirmed training-data leakage risk

- FACT (from the model card): FinBERT was fine-tuned on **Financial PhraseBank (Malo et al., 2014)**.
- CONSEQUENCE: evaluating sentiment accuracy on Financial PhraseBank, **or its Kaggle mirror** ("Sentiment
  Analysis for Financial News" by `ankurzing`, which is a re-upload of the same PhraseBank sentences), would
  be leakage and is explicitly forbidden by this project's own rules.
- **Decision:** sentiment evaluation uses the **validation split** of `zeroshot/twitter-financial-news-sentiment`
  (2,486 rows, disjoint from FinBERT's fine-tuning data and from the rows used for the social replay stream).
  Train split of that dataset is used for the social-source replay; validation split is reserved only for
  `src/eval/` scoring, so the same rows are never both "demoed" and "scored" in a way that could blur the two
  purposes.

## 5. FRED API — rates/credit spreads

- FACT: free API key, instant signup. Rate limit: 30 req/min unauthenticated, 120 req/min with a key.
- ASSUMPTION (to verify per-series at Phase 4, not blocking Phase 0): ICE BofA option-adjusted spread series
  (e.g. `BAMLH0A0HYM2` high-yield, `BAMLC0A0CM` IG) typically have history back to the late 1990s, but exact
  start dates differ per series and will be checked when the shock library is built.

## 6. US Treasury daily par yield curve

- FACT: free, no key. CSV: `.../daily-treasury-rates.csv/<year>/all?type=daily_treasury_yield_curve&field_tdr_date_value=<year>&_format=csv`.
  XML also available. Maturities: 1,1.5,2,3,4,6 months; 1,2,3,5,7,10,20,30 years (plus some bill-specific tenors).
- **Decision:** primary discount-curve source for bond/swap pricing in Module B, date-stamped per snapshot used.

## 7. yfinance

- FACT: free, no key, widely used Python wrapper around Yahoo Finance endpoints.
- ASSUMPTION: Yahoo's undocumented endpoints occasionally throttle/break without notice — this is a known
  community issue, not independently re-verified here. JUDGMENT: cache every pulled series to `data/cache/`
  so the demo never depends on live Yahoo availability at pitch time.

## Net effect on scope

- News: GDELT (primary, live+replay) + NewsAPI (optional, live-only, non-blocking).
- Social: `zeroshot/twitter-financial-news-sentiment` replay (not live) — documented limitation.
- Sentiment eval: `zeroshot/twitter-financial-news-sentiment` validation split (confirmed no overlap with
  FinBERT's fine-tuning data).
- Rates: US Treasury par curve + FRED credit spreads.
- Equities: yfinance.
