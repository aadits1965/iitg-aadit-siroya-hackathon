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
  - **This is a static replay, not a live feed.** The README and deck say this plainly — it satisfies
    "ingest from ≥2 distinct source *types*" (news vs. social) honestly, but social ingestion is not
    real-time in this build. Logged as a stated limitation, not hidden.

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

## 8. Addendum (2026-10-04, post-Phase-0 review) — live social source, GDELT depth/fields, dev-sandbox network constraint

### Live social source: Bluesky vs Mastodon
- FACT: Bluesky's unauthenticated public endpoint (`public.api.bsky.app/xrpc/app.bsky.feed.searchPosts`) returned
  **HTTP 403** from this environment, with and without a browser-like User-Agent. Not usable as-is.
- FACT: **Mastodon public hashtag timelines work with no auth** — tested live:
  `GET https://mastodon.social/api/v1/timelines/tag/stocks?limit=2` returned `200 OK` with real posts, each
  carrying a `created_at` timestamp (e.g. `"2026-10-02T15:46:09.000Z"`). Response headers show a published
  rate limit: `x-ratelimit-limit: 300` requests per 5-minute window, `x-ratelimit-remaining` /
  `x-ratelimit-reset` returned on every call.
- **Decision:** Mastodon hashtag timelines (`#stocks`, `#investing`, `#financial`, etc., across one or more
  public instances) become the **live** social adapter. The `zeroshot/twitter-financial-news-sentiment`
  dataset remains the **offline replay fallback** (`--demo` mode / when Mastodon is unreachable), exactly as
  suggested. Both paths feed the same normalised record schema (§Phase 1).

### Does the tweet-replay dataset have timestamps? → No. Event study moves to GDELT.
- FACT: queried the dataset's actual schema via the HF datasets-server `/info` endpoint. Features are
  **only** `text` (string) and `label` (int64) — no date/timestamp field exists in either split.
- CONSEQUENCE: this dataset cannot be used for the Phase 3 impact-score event study (no way to align a post
  to a trading day). **The event study will be built entirely on timestamped GDELT headlines instead**, as
  instructed.

### GDELT DOC 2.0: historical window, and title-only vs full body
- FACT (from GDELT's own blog post titles/docs): the DOC 2.0 API's searchable index covers back to
  **2017-01-01**, but a given query is only guaranteed effective over a bounded recent window — GDELT's own
  "DOC 2.0 Updates: 1.5 Year Searching" post indicates the practical per-query search window was extended
  from 3 months to roughly 1.5 years, not unlimited. JUDGMENT: treat per-query lookback as **up to ~1.5 years,
  not indefinite**, and verify the actual usable range empirically once live queries succeed (see constraint
  below) before sizing the event-study sample.
- FACT: the DOC 2.0 `artlist`/JSON mode returns these fields only: `url`, `url_mobile`, `title`, `seendate`
  (format `YYYYMMDDTHHMMSSZ`), `domain`, `language`, `sourcecountry`, `socialimage`. **There is no article-body
  field.** GDELT DOC is a metadata/headline index, not a full-text source.
- **Design constraint, to be stated in README + docs/ASSUMPTIONS.md:** this project's NLP runs on
  **headline-level text only** for the GDELT-sourced news channel (title + any short social/meta description
  available), not full article bodies. No article scraping is performed — scraping full bodies would mean
  fetching and redistributing third-party publisher content beyond what GDELT's own CC0 metadata licence
  covers, which this project avoids entirely.

### Dev-sandbox network constraint (does not affect the end-user's own machine)
- FACT: from this development environment's outbound IP, **GDELT DOC 2.0 consistently returns HTTP 429**
  ("Please limit requests to one every 5 seconds…") on every attempt, including after 5s, 20s, and 45s+ waits
  and with a minimal single-field query — i.e. not a simple per-request cooldown, but this IP/IP-range already
  over GDELT's ceiling, most likely because this sandbox's egress IP is shared across many concurrent agent
  sessions. The same pattern showed up on other publisher endpoints tested from here (Yahoo Finance RSS → 429,
  CNBC RSS → 403 Akamai block), confirming it's an IP-reputation issue with this sandbox, not specific to GDELT.
- FACT: **Google News RSS** (`news.google.com/rss/search?q=...`) was reachable (200 OK) from this same
  environment and returns titled, linked, dated items. However, its feed explicitly states: *"made available
  solely for the purpose of rendering Google News results within a personal feed reader for personal,
  non-commercial use. Any other use... is expressly prohibited."* JUDGMENT: fine to use for **ephemeral
  live-mode fetching** (a personal, non-commercial prototype matches its stated terms) but its content must
  **never** be bulk-cached into `/data` for redistribution in the public repo — that would exceed the licence.
- **Decision:**
  1. The GDELT adapter is built fully correct against GDELT's real, documented schema (confirmed above), with
     retry/backoff on 429. It will work from a normal (non-shared, non-datacenter) network — i.e. the
     candidate's own machine: run `python scripts/build_cache.py` once from a normal network connection to
     populate a real, redistributable `data/cache/news_gdelt.jsonl` before the demo.
  2. Parsing/dedup logic is unit-tested against **fixture JSON shaped exactly like GDELT's real schema**
     (field names/format confirmed live above), clearly labeled as test fixtures, never presented as real
     fetched articles.
  3. Mastodon (confirmed working from this sandbox right now) is used to pull **real, live, cached** social
     data today, so at least one channel's `data/cache/` content is genuinely live-fetched rather than only a
     fixture.

## 9. Addendum (2026-10-04) — real market-data snapshot via an AI-assisted web-fetch tool; Fed stress-scenario sourcing

- FACT: this dev sandbox's **direct** requests calls to treasury.gov (HTTP 000, connection failure) and
  yfinance/Yahoo Finance (JSON-decode failures, consistent with a 429-style block) fail, exactly like GDELT.
  However, **an AI-assisted web-fetch tool (its output passes through a summarising model) reached both
  successfully** — a different network path than this sandbox's direct outbound requests. Used to pull one
  real, dated snapshot: the US Treasury par yield curve as of 2026-10-02
  (`data/cache/market/treasury_par_yield_curve.csv`) and spot prices for SPY/AAPL/MSFT/NVDA/JPM as of the
  same date (`data/cache/market/equity_prices.csv`), both files stamped with exactly how and when they
  were fetched. This is real, live-verified data, not training-knowledge or fabrication — but it is a
  single-date snapshot, not a time series, and cannot substitute for the full historical window
  `scripts/build_cache.py` needs to build for the event study (GDELT itself still returns 429 through this
  same tool, confirmed by testing it directly — this path doesn't unblock the news side).
- FACT: the Treasury CSV's exact column format was confirmed live via this tool:
  `Date,"1 Mo","1.5 Month","2 Mo","3 Mo","4 Mo","6 Mo","1 Yr","2 Yr","3 Yr","5 Yr","7 Yr","10 Yr","20 Yr","30 Yr"`,
  `MM/DD/YYYY` date format. `src/ingestion/market_data.py`'s parser is built against this confirmed format
  and unit-tested against it verbatim (`tests/test_market_data.py`, 2/2 passing) rather than guessed.
- FACT: Federal Reserve severely-adverse stress-test scenario magnitudes, fetched live from
  `federalreserve.gov/publications/2025-november-proposed-2026-stress-test-scenarios.htm` (2026-10-04):
  equity prices fall ~54%, 10-year Treasury yield falls ~2.0pp (4.3%→2.3%), BBB-10Y spread widens 4.4pp
  (to 5.7pp), VIX peaks at 72, unemployment rises 5.5pp to a 10% peak, house prices fall ~29%, commercial
  real estate falls ~40%. Used directly (with citation) for Module B's "severe" shock tier in
  `config/scenarios.yaml`; every other tier/number in that file not drawn from this citation is explicitly
  labelled an illustrative assumption, not a second sourced figure.

## 10. Addendum (2026-10-04, post-Phase-4 review) — Fed scenario re-sourced from the raw table, not a summary

- FACT: `federalreserve.gov` is reachable with a **direct** `curl`/`requests` call from this dev machine
  (HTTP 200) — unlike `treasury.gov` (HTTP 000) and Yahoo Finance (429/JSON errors). This means the earlier
  Fed-scenario figures, originally obtained via the AI-assisted web-fetch tool (which passes content
  through a summarising model), have now been **re-extracted directly**: `curl` the real HTML page, then
  parse its embedded `<table>` elements with a plain regex/HTML strip — no summarising model in the loop at
  all.
- FACT: the page embeds the Federal Reserve's actual quarter-by-quarter severely-adverse domestic scenario
  table (`Date, Real GDP growth, Nominal GDP growth, Real/Nominal disposable income growth, Unemployment
  rate, CPI inflation, 3-month Treasury rate, 5-year Treasury yield, 10-year Treasury yield, BBB corporate
  yield, Mortgage rate, Prime rate, Dow Jones Total Stock Market Index, House Price Index, Commercial Real
  Estate Price Index, Market Volatility Index`), quarterly from Q1 2026 through Q1 2029. Full extracted
  table saved to the session scratchpad; key rows:

  | Quarter | 10-yr Treasury | BBB yield | BBB−10yr spread | VIX |
  |---|---|---|---|---|
  | Q1 2026 (jump-off) | 3.2% | 7.6% | 4.4pp | 58.8 |
  | Q2 2026 | 2.7% | 8.2% | 5.5pp | **72.0** (peak) |
  | Q3 2026 | 2.4% | 8.1% | **5.7pp** (peak) | 70.8 |
  | Q4 2026 | **2.3%** (trough) | 7.8% | 5.5pp | 66.5 |

  This **independently re-derives** (via the table's own raw numbers, computing BBB-yield minus 10-yr-yield
  myself) the exact figures the Board's prose states separately ("VIX... peak of 72 percent in the second
  quarter", "spread... reaching a level of 5.7 percentage points", 10-yr "to 2.3 percent... by the fourth
  quarter of 2026") — the prose and the raw table agree exactly, which is strong corroboration the earlier
  tool-summarised figures were accurate, but this raw-table extraction is now the citation used in
  `config/scenarios.yaml`, not the earlier summary.
- FACT: the **baseline** (non-stress) scenario's own table gives a real, sourced pre-stress VIX figure —
  23.4 at Q1 2026 — used as `vix_baseline` in the "fed_severely_adverse" and "geopolitical_rate_shock"
  tiers, replacing the earlier illustrative guess of 18.
- Downloaded the official PDF (`2026-proposed-supervisory-stress-test-scenarios-20251024.pdf`, 1.86MB,
  confirmed real PDF via `file`) as a further corroborating source, not yet cross-parsed page-by-page given
  the HTML table already gives the authoritative raw figures directly.
- **This Fed-scenario data is SOURCED, not PROVISIONAL** (direct download, no summarising model). The
  Treasury par-yield curve and the five equity spot prices in `data/cache/market/` remain **PROVISIONAL**
  (fetched via the AI-assisted web-fetch tool, summarising model in the loop) — those are marked with
  `provisional: true` in their
  file headers and `YieldCurve.is_provisional` is checked and surfaced by `scripts/run_stress_test.py`.
  `scripts/verify_provisional_data.py` cross-checks them against a direct download once run from a normal
  network; nothing from them should be treated as deck-ready until that check passes.

## 11. Addendum (2026-10-04, post-Phase-4 review) — entity-linking precision audit

**Provenance note, stated plainly: every TP/FP judgment in this section (and in section 13 below) was made
by the AI assistant reading each headline, not independently verified by the candidate.** This is different
from the event-classification gold set (`data/eval/event_gold.csv`), which the candidate hand-labelled
blind himself (see "Gold-set contamination found and fixed" below) — the entity-linking numbers here are an
AI-generated measurement of the AI's own code fix, useful as a documented, mechanically-reproducible check
of the fix's direction and rough magnitude, but not a human-verified precision figure. For that reason
these specific numbers (30% / 91.7% / 94.5%) are not presented in the deck or README as a candidate-
verified result — they're kept here, with this note, for full transparency about how they were produced.

Requested check: sample 50 real, wide-universe-linked headlines and measure precision.
`scripts/audit_entity_linking.py` draws the sample (seed 42); the AI assistant read every row's text and
judged TP/FP by hand; the labelled sample is committed at `data/eval/entity_linking_audit.csv`.

**Before any fix:** an earlier, informal pass over a larger (171-doc) linked pool found precision around
**30%** (18 correct / 61 total ticker matches), dominated by two bugs:
1. The bare word "Target" (an alias for Target Corp) matched the ubiquitous financial-news phrase
   "price target" / "stock price target" — by far the largest single source of false positives, and
   exactly the pattern the review flagged as a risk (also checked: Visa, Apple, Oracle).
2. Bare ticker symbols were matched as free text case-insensitively, so the verb "ups" ("Barclays ups to
   Overweight") matched United Parcel Service (ticker UPS).
A third, smaller pattern: a sell-side bank's own name appearing only as the **source** of a rating action
on a *different* company ("Autodesk downgraded ... at JPMorgan") was being attributed as an affected
entity — this is the exact bug already caught independently while reviewing the engine's real signal
output (the Autodesk/JPMorgan signal, since fixed and visible in the diff between the pre- and post-fix
`results/signals.jsonl`).

**Fixes** (`src/nlp/entity_linking.py`):
1. `AMBIGUOUS_BARE_ALIASES = {"target", "visa", "apple", "oracle"}` — these four names are excluded from
   free-text alias matching; only the fuller legal name ("Target Corp.") or a `$CASHTAG` still matches.
2. Ticker symbols are matched **only** via an explicit `$CASHTAG` regex (case-sensitive), never as a
   free-text alias — fixes the "ups"/UPS collision at the root rather than as a one-off.
3. `_is_analyst_source_mention()`: a lightweight heuristic (checks ~10 chars before / ~22 chars after the
   match for subject markers like "stock"/"shares" vs. source indicators like "upgrades"/"at "/"reels in")
   suppresses a bank's own ticker when it looks like the source of a rating action on someone else, for
   `{JPM, BAC, MS, WFC, GS, C}`. Documented as imperfect — it still misses a bank name at the very end of a
   headline with no adjacent verb (e.g. "... — BofA"), which is a known remaining gap, not silently claimed
   to be solved.
4. **A fourth, unrelated bug the regression tests caught in the process**: the original `\bALIAS\b` regex
   silently fails to anchor after an alias ending in punctuation (`\b` only fires at a word/non-word
   transition, and "Corp."/" " are both non-word, so there's no transition) — this affected most of the
   universe's full legal names ("Target Corp.", "Apple Inc.", "JPMorgan Chase & Co.", etc.). Fixed by
   switching to `(?<!\w)...(?!\w)` lookarounds.

**After the fixes**, re-scoring the same committed 50-row sample: **44 / 48 ticker matches correct = 91.7%
precision** (`data/eval/entity_linking_audit.csv`, `verdict_tp_or_fp` column). The 4 remaining false
positives are all the same documented gap: a bank name at the very end of a headline/tweet with no
adjacent rating-action verb for the heuristic to key off (e.g. `"$NVDA - Nvidia set for gaming tailwinds -
BofA"` — BAC still gets attributed). 12 regression tests added
(`tests/test_entity_linking_precision.py`) pinning the specific headline patterns above so they can't
silently regress; full suite 100/100 passing.

**Downstream effect:** these are the same linking functions the core 20-ticker engine uses, not just the
wide event-study universe — the Autodesk/JPMorgan false positive was already visible in the real signal
output before this fix. `results/signals.jsonl` and `results/stress_test_output.json` were regenerated
after the fix (86 signals, down from 89; 6 fired stress tests, down from 8 — the removed signals/triggers
were exactly the ones built on a now-corrected false-positive entity link).

## 12. Addendum (2026-10-04, second post-Phase-4 review) — event classification: analyst actions vs credit events

Requested check: confirm whether the headline behind the "Disney credit downgrade" signal was a genuine
credit-rating action or an equity-analyst action, and fix the classifier if conflated.

**Confirmed from real signal data** (`results/signals.jsonl`, signal `sig_62fabd059044e2ab` in the pre-fix
run): the exact headline was **"Disney downgraded as analyst says parks attendance could take 2 years to
'normalize'"** — explicitly an equity-analyst stock-rating opinion (the word "analyst" is right there), not
a credit-rating-agency action (no Moody's/S&P/Fitch, no bond/debt language). The rule classifier tagged it
Credit Event at 0.99 confidence purely because the keyword list contained bare "downgrade".

**Fix** (`src/nlp/event_classification.py`): "downgrade" now only counts toward Credit Event when the text
also contains explicit credit-market vocabulary (`CREDIT_MARKET_INDICATORS`: Moody's/S&P/Fitch, "credit
rating", "bond"/"bonds", "junk status", etc.). A first attempt gated the *opposite* way (requiring explicit
analyst words like "analyst"/"price target" to be *present* to suppress "downgrade") but a re-run of the
full engine immediately surfaced a second real false positive it missed — **"Take-Two downgraded on murky
game slate"**, a terse headline with no explicit analyst word at all — so the rule was inverted to the more
conservative default: bare "downgrade" never counts unless credit-market language is present, since
equity-analyst "downgrade" vastly outnumbers genuine credit-rating downgrades in a retail/social feed. 7
regression tests added pinning both real cases plus the "still works for a genuine credit event" case.

**A second, unrelated bug surfaced while re-verifying the regenerated headline output**: the new top
triggered signal ("Bernstein turns bullish on VMware's valuation") was itself spuriously tagged
Geopolitical. Tracing it back: the signal was a 5-document cluster of unrelated analyst notes ("Moody's
warns on Harley-Davidson", "BAML warns of profit pressure for Hormel", "Jefferies warns on L Brands", etc.)
that all got the GEOPOLITICAL macro-tag because the keyword "war" was matched as a **bare substring inside
"warns"** (`"war" in "warns".lower()` is `True`) — the same root-cause bug (naive substring matching on a
short keyword) existed in both `entity_linking.py`'s `MACRO_KEYWORDS` and `event_classification.py`'s
`RULE_KEYWORDS["Geopolitical"]`. Fixed in both files by switching every keyword check to a
`(?<!\w)...(?!\w)` word-boundary regex (same technique already used for entity aliases). 4 more regression
tests added (2 per file: "warns" no longer spuriously tags Geopolitical, a genuine "war" mention still
does).

**Re-ran the full pipeline after both fixes**: `results/signals.jsonl` regenerated (76 signals, down from
86 before this round), fired stress tests down to 3 (from 6). The real headline scenario is now **"US stock
futures slip ahead of #inflation report"**, correctly classified Macroeconomic, firing the
`fed_severely_adverse` scenario — a clean, genuinely macro-economic trigger, not an artifact of either bug.
112/112 tests passing.

## 13. Addendum (2026-10-04) — entity-linking precision with CIs, a fresh sample, and a targeted recall check

**Wilson 95% CI for the originally-reported 91.7% figure**: 44/48 correct, **Wilson 95% CI [80.4%, 96.7%]**
(computed directly — `statsmodels` isn't installed in this environment, so the closed-form Wilson
score-interval formula was used, not approximated).

**Fresh, independent sample** (not used for any rule-fixing): the original audit had already used 50 of the
only 64 wide-universe-linked documents available in the cached corpus at the time, so there weren't 50
genuinely unused ones to draw a second sample from. Rather than reuse the thin remainder, 600 additional
real rows were pulled from the same MIT-licensed HF dataset (`train` split, **offset=300**, rows the
pipeline had never touched — see `data/cache/_fresh_audit_pool.jsonl`), which produced 68 newly-linked
documents. 50 were sampled (seed 123, distinct from the original seed 42) and hand-labelled the same way:
**52/55 ticker matches correct = 94.5%, Wilson 95% CI [85.1%, 98.1%]**
(`data/eval/entity_linking_audit_fresh.csv`). **Pooled across both samples: 96/103 = 93.2%, Wilson 95% CI
[86.6%, 96.7%]**. Two further real gaps surfaced in the fresh sample (documented, not fixed, given the
instruction to move to Phase 5 after this round): "Moody's" as a ratings-agency *source* on an unrelated
bank-liquidity story (MCO isn't in `ANALYST_SOURCE_TICKERS`, so the source-suppression heuristic never
runs for it), and "Wells Fargo **analyst** Dori Kesten..." (the word "analyst" itself was never in the
`_SOURCE_INDICATORS` list, a one-line gap).

**Recall spot-check**: a first attempt — sampling 80 documents where the strict linker found *no* ticker
but a loose, unbounded substring match of any company name/alias did — turned out to be dominated almost
entirely by noise (only 2 of 80 were genuine company mentions; the other 78 were "price target"/"Intelsat"
("intel" substring)/"upside" ("ups" substring) false candidates), confirming genuine recall failures are
rare in this corpus rather than giving a usable 30-headline sample. Switched to a **targeted** check instead:
searched the full ~973-document corpus (all three real sources combined) for every bare, word-boundary
occurrence of the four originally-excluded ambiguous aliases (Target/Visa/Apple/Oracle) and hand-labelled
every one found, rather than a generic random sample:
- **"target": 151 occurrences, 0/151 were genuine Target Corp mentions** (150 were the generic "price
  target"/"stock price target" phrase, 1 was a different real company, "Target Hospitality", correctly not
  confused with Target Corp) — excluding it cost **zero measured recall** in this entire corpus.
- **"apple": 5 occurrences, 5/5 were genuine Apple Inc. mentions** ("Apple Shares"/iPhone production,
  "Apple Has 40% Upside", "Apple Card", "Apple closing all China stores", "Apple saw China iPhone units
  fall") — **100% recall loss** for the four weeks headlines actually written this way, zero offsetting
  false-positive benefit ever found.
- **"oracle": 1 occurrence, 1/1 genuine** ("Oracle's Need for 'Steep' Sales Climb...") — same conclusion.
- **"visa": 0 occurrences either way** in this corpus — the exclusion is untested here, kept as a
  precaution since there's no counter-evidence, but also no confirming evidence.

**Consequence**: given this direct evidence, "apple" and "oracle" were **removed** from
`AMBIGUOUS_BARE_ALIASES` (kept only "target" and "visa") — the recall check changed the actual shipped
rule, not just the measurement. 2 more regression tests added confirming bare "Apple"/"Oracle" now match.
Re-ran the full pipeline once more after this change; 112/112 tests passing.

## 14. Addendum (2026-10-19) — correction: the provisional curve was never wrong; the comparison was

**This retracts a conclusion reached during the 2026-10-18 local-run fixes** (previously recorded here and
in `docs/ASSUMPTIONS.md` as the provisional Treasury curve being off by 38-141bp at every tenor, called a
"transcription error"). That conclusion was itself based on a bug, not a real data-quality problem, and is
withdrawn.

**What actually happened:** `src/ingestion/market_data.py::fetch_treasury_curve()` took the CSV response's
*last line* on the (wrong) assumption the file is sorted ascending by date. Treasury's annual file is
actually sorted **descending** (newest first), so the last line was the year's **first** business day
(2026-01-02) — not the latest, as the code's own docstring claimed. The direct-fetch comparison that
produced the "38-141bp" figure was therefore comparing the provisional snapshot's stated date (2026-10-02)
against a wrongly-selected 2026-01-02 row — a ~9.5-month-earlier curve — not against the real 2026-10-02
market.

**Re-checked directly, per tenor, against the correct 2026-10-02 row from a fresh direct fetch:** every
one of the 12 published tenors (1Mo through 30Yr) matches the provisional snapshot **exactly, 0bp
difference at every point** (full table in `docs/ASSUMPTIONS.md`, "Treasury curve `as_of` bug"). The
provisional snapshot, relayed via the AI-assisted web-fetch tool, was accurate for its stated date the
entire time.

**Fix:** `fetch_treasury_curve()` now parses every row's date and selects the maximum, regardless of file
order. Re-fetched: `as_of: 2026-10-16` (the genuinely latest available business day, 199 rows parsed). 3
tests in `tests/test_market_data.py` (including an explicit out-of-order-rows regression test) guard
against this specific bug recurring.

## Net effect on scope (superseded fields updated by §8 addendum above)

- News: GDELT (primary, live+replay, headline-level only — no article body) + NewsAPI (optional, live-only,
  non-blocking) + Google News RSS (ephemeral live-mode use only, never cached/redistributed).
- Social: **Mastodon public hashtag timelines (live adapter, confirmed working, timestamped)**, with
  `zeroshot/twitter-financial-news-sentiment` as the **offline replay fallback** (confirmed no timestamps,
  so replay-only, and excluded from the event study).
- Sentiment eval: `zeroshot/twitter-financial-news-sentiment` **validation split**, used strictly for scoring
  only — no threshold, label-mapping, or weight tuning is done on it (tuning happens on train split / fixed
  a-priori rules only; see docs/ASSUMPTIONS.md).
- Impact-score event study (Phase 3): **GDELT timestamped headlines**, not the tweet dataset (which has no
  dates).
- Rates: US Treasury par curve + FRED credit spreads.
- Equities: yfinance.
- **Known dev-environment constraint:** GDELT and several publisher RSS feeds return 429/403 from this
  sandbox's shared egress IP. Code is written against GDELT's confirmed-real schema either way; a one-time
  cache-build run from a normal network is required before the demo.
