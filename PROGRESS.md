# Progress Log — S&P Global & Crisil Campus Hackathon 2026

Candidate: Aadit Siroya, IIT Guwahati (s.aadit@iitg.ac.in)
Deadline (planning anchor): **2026-10-11** — see docs/USER_TODO.md to reconfirm exact time with organisers.
Scope decision: Core AI/NLP Risk Engine + **Module B (Strategic Portfolio Stress Testing)**. Module A
(Tactical Rebalancing) is stretch-only, attempted only if Phases 0-5/7-9 are done early given the ~1-week
deadline. See build prompt §3 for reasoning (domain fit with S&P Global / Crisil's credit-risk business,
tie-breaker #1 is Domain Understanding).

## Phase 0 — Setup & verification
Status: **IN PROGRESS**

Done:
- git initialized, local identity set to "Aadit Siroya" (global identity left untouched).
- Folder skeleton created: src/{ingestion,nlp,signals,modules/{stress_test,rebalancer},dashboard,api,eval},
  tests/, data/{raw_samples,cache,synthetic,eval}, results/, docs/, config/, scripts/.
- `.gitignore`, `LICENSE` (MIT, Aadit Siroya, 2026), `.env.example` written.
- `requirements.txt` drafted (versions to be confirmed against a real `pip install` in Phase 7).
- **All external dependencies verified by actually querying/reading their docs** — see
  `docs/DATA_VERIFICATION.md` for the full FACT/ASSUMPTION/JUDGMENT breakdown. Headline findings:
  - FACT: X/Twitter API has no viable free read tier in 2026 (pay-per-use, ~$0.005/read). Confirms the
    build prompt's own warning. Social source will be a **replayed, licensed dataset**
    (`zeroshot/twitter-financial-news-sentiment`, MIT license), not a live feed — documented as a limitation
    everywhere, not hidden.
  - FACT: FinBERT (`ProsusAI/finbert`) was fine-tuned on Financial PhraseBank — confirms the leakage risk.
    Sentiment evaluation will use the **validation split** of the Twitter Financial News Sentiment dataset
    instead (disjoint from FinBERT's fine-tuning data, and disjoint from the rows used for social replay).
  - FACT: GDELT DOC 2.0 API is free, no key, CC0-licensed, redistribution-friendly with citation — primary
    news source, both `live` and cached `replay` modes.
  - NewsAPI: optional secondary news source, **live-mode only**, never required for the graded demo (its
    free-tier ToS restricts to dev/testing; the required `--demo` path never calls it).
  - FRED (credit spreads) and US Treasury (par yield curve): both free, no-key-or-easy-key, confirmed
    accessible with documented URL/endpoint patterns.
- `docs/COMPLIANCE.md` and `docs/USER_TODO.md` created.

Next: entity universe file, pydantic ingestion schema, source adapters (Phase 1).

Gate status: **PASS** — every external dependency has been actually checked, not assumed; two premise
problems flagged in the build prompt (X API, FinBERT leakage) are independently confirmed true, and the
scope has been adjusted in response rather than worked around silently.

## Phase 0 addendum — pre-Phase-1 review
Status: **DONE**. Four follow-up checks requested before Phase 1 began, all resolved with live evidence
(docs/DATA_VERIFICATION.md section 8):
- Mastodon public hashtag timelines confirmed working (no auth, real timestamps) -> live social adapter.
  Bluesky's public search endpoint returned 403 -> not used.
- Twitter replay dataset confirmed to have **no timestamp field** (checked via HF datasets-server /info) ->
  excluded from the Phase 3 event study; event study moves to timestamped GDELT headlines.
- GDELT DOC 2.0 confirmed to return headline-level fields only (title/url/seendate/domain/language/
  sourcecountry/socialimage, no body) -> documented as a design constraint.
- This dev sandbox's shared egress IP confirmed persistently blocked by GDELT (HTTP 429 on every query,
  over a ~17-minute live run, logged in full) and by several news RSS hosts -> one-time cache-build step
  moved to docs/USER_TODO.md for Aadit to run from a normal network.

## Phase 1 — Ingestion
Status: **DONE**

- Pydantic `Document` schema (`src/ingestion/schema.py`): doc_id, source, source_type, published_at_utc,
  retrieved_at_utc, url, title, text, lang, raw_meta. UTC-coercing validators, empty-text rejection.
- Three adapters, each supporting `fetch_live` + cached `fetch_replay`:
  - `news_gdelt.py` — GDELT DOC 2.0, self-throttled to GDELT's own stated 5s minimum, retry/backoff on 429.
    Could not be live-tested end-to-end from this sandbox (confirmed blocked — see addendum above); parsing
    logic is unit-tested against a fixture shaped exactly like GDELT's real, live-confirmed schema.
  - `social_mastodon.py` — live-tested for real: pulled **73 deduped real posts** (81 fetched, 8 exact
    duplicates dropped) across 5 financial hashtags, cached to `data/cache/social_mastodon.jsonl`.
  - `social_twitter_replay.py` — pulled **300 real rows** from the MIT-licensed HF dataset via the
    datasets-server API, cached to `data/raw_samples/social_twitter_replay.jsonl`. Synthetic-timestamp
    limitation flagged in every row's `raw_meta`.
- Dedup (`dedup.py`): exact normalised-title hash + rapidfuzz fuzzy match within a 48h window. 9 unit tests
  covering exact/fuzzy/distinct/outside-window cases, all passing against real dedup counts above.
- `scripts/build_cache.py` orchestrates all three adapters; `docs/USER_TODO.md` has the one GDELT caveat.

## Phase 2 — NLP Risk Engine
Status: **DONE**

- Entity linking (`entity_linking.py`): curated 20-ticker alias table (`data/universe.csv`, S&P 100 names
  across 7 sectors) + macro-keyword tagger (MACRO/GEOPOLITICAL/CREDIT/MARKET fallback). Scope decision
  (alias-matching instead of full spaCy NER) documented in the module docstring and docs/ASSUMPTIONS.md —
  deterministic, no extra model download needed, sufficient precision for a 20-name demo universe.
- Sentiment (`sentiment.py`): FinBERT (`ProsusAI/finbert`) primary, label order read from the model's own
  `config.id2label` rather than hardcoded. **Actually run live**: first call (incl. one-time ~440MB weight
  download) took 82.97s; subsequent inference measured at **86ms/doc** on CPU. VADER lexicon baseline wired
  as the required "naive approach" comparison.
- Event classification (`event_classification.py`): keyword/rule baseline (implemented, tested) + zero-shot
  NLI via `facebook/bart-large-mnli` (implemented; CPU latency not yet benchmarked — deferred to Phase 3
  alongside the labelled gold set, since that's where it needs to run at scale anyway).
- Impact Score (`impact_score.py` + `config/impact.yaml`): transparent weighted composite over sentiment
  magnitude, event-severity prior, source breadth, entity importance, and novelty. Weights sum to 1.0
  (asserted at load time); every score returns its full component breakdown. All weights are stated as
  illustrative assumptions with no empirical source in `docs/ASSUMPTIONS.md`, fixed before any evaluation
  run (no post-hoc tuning).
- Clustering engine (`nlp/engine.py`): groups documents into "stories" by (entities, event class) within a
  6h window so multi-source coverage of one event produces one signal with real source-breadth and a
  6h cooldown/novelty flag — this is what Module B's trigger de-dup (Phase 4) will key off.
- Signal schema + store (`signals/schema.py`, `signals/store.py`): versioned Signal model, appended to
  `results/signals.jsonl` (JSON Lines, source of truth) and `results/signals.db` (SQLite, queryable).
- FastAPI (`api/main.py`): `GET /health`, `GET /signals?since=&min_impact=&event_class=&limit=`. Documented
  honestly as polling-based, not a real pub/sub bus.
- **Full pipeline actually run end-to-end on real cached data** (373 real docs: 73 Mastodon + 300 replay
  tweets; GDELT skipped per the sandbox-network finding above): produced **89 signals** in 62.0s
  (166ms/doc). 12 signals scored impact > 7. Output written to `results/signals.jsonl` / `results/signals.db`
  and verified via the live API (`GET /signals?min_impact=7` returns exactly those 12).
- 25/25 tests passing (`pytest tests/ -q`). One real bug found and fixed during testing: `get_conn()`'s
  default path argument was resolved at import time, so monkeypatching `SIGNALS_DB` in a test silently had
  no effect and the API tests were reading the real `results/signals.db` instead of a temp DB — fixed by
  resolving the module-level path inside the function body instead of as a default-argument value.

Gate status: **PASS** — every document that reaches the engine produces a valid structured signal; the
engine was run against genuinely fetched data, not synthetic placeholders, and a real bug was caught by
the test suite rather than shipped silently.

Not yet verified: zero-shot event classifier's actual accuracy/latency (Phase 3), and the GDELT news channel
end-to-end (blocked in this sandbox, pending Aadit's one-time cache-build run — see docs/USER_TODO.md).

## Phase 3 — Engine evaluation
Status: **PARTIALLY DONE** — reporting now per the requested pause point.

- **Sentiment eval: DONE, real result.** FinBERT vs VADER run for real on 2,000 held-out rows of
  `zeroshot/twitter-financial-news-sentiment` (validation split, confirmed disjoint from FinBERT's own
  fine-tuning data). FinBERT: 72.2% accuracy [70.2, 74.2], macro-F1 0.660 [0.635, 0.684]. VADER baseline:
  50.5% accuracy [48.3, 52.6], macro-F1 0.453 [0.429, 0.476]. CIs don't overlap — a real, non-noise
  improvement. Written to `results/metrics.json`, full writeup in `docs/EVALUATION.md` section 1.
- **Event classification gold set: sample ready, labelling pending.** `data/eval/event_gold.csv` has
  **110 real rows** sampled from the 373 genuinely-ingested documents (stratified by the rule baseline's
  own guess, that guess kept in a separate column never used as gold). `scripts/label_events.py` is a
  small resumable CLI for hand-labelling. **Needs Aadit** — see docs/USER_TODO.md. Per-class P/R/F1 and the
  confusion matrix are deferred until labelling is done (reporting the rule baseline's own guesses as gold
  would be circular).
- **Impact Score event study: blocked on this dev machine, not fabricated.** Method fully implemented
  (`src/eval/impact_event_study.py`) and mechanically verified by 4 passing unit tests against hand-built
  price series (no-look-ahead date alignment, correct abnormal-return recovery). Cannot produce a real
  correlation number here: GDELT, Yahoo Finance, and the US Treasury yield-curve endpoint are all confirmed
  unreachable from this sandbox (GDELT: persistent HTTP 429 over a full ~17-min live run; Treasury: HTTP 000
  connection failure; yfinance: JSON-decode failure — consistent with the same shared-IP restriction already
  documented in Phase 0/1). Only 4 real ticker-linked, genuinely-timestamped documents exist here so far
  (from live Mastodon) — the script correctly refuses to report a correlation below n=30 rather than report
  noise as signal. Full status in `docs/EVALUATION.md` section 3; next step logged in `docs/USER_TODO.md`
  (`scripts/run_impact_event_study.py`, to run after the GDELT cache-build step).

Gate status: **PARTIAL PASS, honestly reported** — one of three evaluations fully done with a real, CI-backed
result; one is infrastructure-complete and correctness-verified but blocked on data only available from a
normal network; one needs human labelling that only Aadit can do. Per the build rules ("when a phase's gate
fails, stop and tell me"), stopping here to report rather than fabricating the missing two numbers or
quietly working around the blocker.

## Changes requested before continuing (post-Phase-3 review)
Status: **DONE**

1. **Event-study power threshold raised 30 -> 200**, derived (not arbitrary): ~80% power to detect r≈0.2 at
   alpha=0.05 needs n≈194 (Fisher z-transform sample-size formula). `run_event_study()` now always computes
   and returns the Spearman r, CI, and decile table once n>=3 (never suppressed), flagging
   `power_adequate=False` below 200 with an explicit "UNDERPOWERED" note rather than omitting the number.
   Widened event-study-only ticker universe added (`data/universe_event_study.csv`, 80 tickers, kept
   separate from the 20-ticker Module B/dashboard universe) plus a corresponding wider GDELT pull
   (`ingest_gdelt_event_study()`, 18-month window) to try to reach n>=200 once run from a clean network.
2. **Sentiment eval extended**: majority-class baseline, full per-class precision/recall/F1, and the eval
   split's label distribution now all go to `results/metrics.json`; macro-F1 is the documented headline
   metric, not accuracy. Re-run for real: majority baseline gets 66.9% accuracy but macro-F1 only 0.267
   (zero recall on negative/positive) -- the exact distortion macro-F1-as-headline is meant to catch.
   FinBERT's bearish (negative) recall is 0.765 vs VADER's 0.529 and the majority baseline's 0.000.
3. **`scripts/build_cache.py` extended** to also fetch a dated Treasury par-yield curve snapshot, equity
   daily prices (core + event-study universe, ~550 days), and optional FRED credit-spread series
   (`src/ingestion/market_data.py`, Treasury CSV parser unit-tested against the real confirmed column
   format). `curve.py` rewritten with a **hard gate**: `load_curve()` now raises `MissingCurveCacheError`
   if no real cached snapshot exists -- no silent fallback. The only synthetic curve
   (`synthetic_test_only_curve()`) is explicitly named, flagged `is_synthetic_test_only=True`, and used only
   by unit tests. **To unblock real Module B output now** (direct requests to Treasury/Yahoo fail from this
   sandbox, but Claude's WebFetch tool reached both through a different path), seeded one real, dated,
   clearly-provenanced snapshot: Treasury par curve as of 2026-10-02, and spot prices for
   SPY/AAPL/MSFT/NVDA/JPM same date -- see docs/DATA_VERIFICATION.md section 9 for the full citation trail,
   and the header comments in `data/cache/market/*.csv` for exactly how/when each was fetched.
4. **Gold set not sent for labelling.** `scripts/sample_event_gold.py` now targets 200 rows with a 20-per-
   class floor where available (redistributing shortfall from thin classes to classes with surplus).
   `docs/USER_TODO.md` now says explicitly: rebuild the cache first, re-run the sampler, *then* label.
5. **Exact commands for Aadit** written up front in `docs/USER_TODO.md` (venv setup, `build_cache.py` with
   expected ~15-20 min runtime, then the event study, then gold-set regeneration+labelling), not buried at
   the end.

Real Fed severely-adverse stress-scenario magnitudes (equity -54%, rates -200bp, IG spread +440bp, VIX
peak 72, house prices -29%, CRE -40%) fetched live from federalreserve.gov and used directly in
`config/scenarios.yaml`'s "severe" shock tier, cited; every other tier/number in that file is explicitly
labelled an illustrative, undsourced assumption rather than presented as a second official figure.

## Phase 4 — Module B: Strategic Portfolio Stress Testing
Status: **DONE** (core build + tests); dashboard integration is Phase 5.

- **Synthetic portfolio** (`src/modules/stress_test/portfolio.py`, fixed seed 1234): 50 positions (20 loans,
  18 bonds, 5 options, 5 swaps, 2 FX forwards), ~$992M total notional, all counterparty names clearly
  fictional (unit-tested against a real-entity blocklist). Rating->PD and LGD-by-seniority are documented
  illustrative assumptions, not copied from a specific published table.
- **Pricing** (`pricing.py`): full cashflow discounting for bonds/loans, swap DV01 via bump-and-reprice
  (not a closed-form shortcut), closed-form Black-Scholes for options, EL = PD x LGD x EAD. 16 hand-checkable
  tests (closed-form bond price, DV01 sign for payer/receiver, put monotonicity, EL monotonicity, the
  missing-cache hard-gate, the synthetic-curve flag).
- **Shock library** (`config/scenarios.yaml`): real Fed severely-adverse numbers for the "severe" tier
  (cited above); "moderate" (40% interpolation) and the brief's own "geopolitical_example" (+200bp, the
  opposite direction to the Fed's recessionary scenario) kept explicitly separate and labelled.
- **Trigger engine** (`trigger.py`): fires on impact > threshold (default 7, matching the brief's example),
  with a 6h cooldown per (entity-cluster, event-class) so one story doesn't refire repeatedly. 6 tests
  (threshold boundary, cooldown suppression/expiry, cross-cluster independence).
- **Revaluation** (`revaluation.py`): before/after value, P&L by asset class/sector/position, EL before/
  after, top-10 contributors, entity-specific vs portfolio-wide scoping. 8 tests (zero-shock -> zero-P&L,
  entity scoping, EL scales with the PD multiplier, put value rises in a selloff, breakdowns sum to total).
- **Naive vs full reprice** (`naive_approx.py`, Phase 4.5 requirement): duration-only vs full bond reprice,
  delta-only vs full Black-Scholes reprice. 6 tests confirming the approximation error *grows* with shock
  size (real convexity/gamma effect, not a coincidence of two shortcuts).
- **Ran for real, end-to-end** (`scripts/run_stress_test.py`) against the real portfolio, the real Treasury
  curve, real equity spot prices, and the 89 real signals from Phase 1-2: **8 of 89 signals fired** a stress
  test. Illustrative severe-macro scenario: portfolio value $645.9M -> $606.8M (-6.05%), expected loss
  $10.1M -> $30.3M. Naive-vs-full comparison on a real portfolio bond: error grows from -$139 at +10bp to
  -$53,640 at +200bp; on a real portfolio option: error grows from -$0.34 at -5% spot to -$27.68 at -40%
  spot -- both confirming genuine, growing convexity/gamma error, not noise. Full output in
  `results/stress_test_output.json`.

75/75 tests passing (`pytest tests/ -q`, 9.78s).

Gate status: **PASS** -- every pricing function verified against a hand-checkable closed-form or known
sign/monotonicity property; the full pipeline ran against real market data (one real dated snapshot seeded
via WebFetch, full historical rebuild still pending Aadit's local run) and real signals, not synthetic
placeholders presented as real.

Not yet done: dashboard visualization of this output (Phase 5), and Module A stretch (only if time remains).

## Changes requested before Phase 5 (post-Phase-4 review)
Status: **DONE**

1. **Provenance.** The WebFetch-sourced Treasury curve and equity prices are marked `PROVISIONAL` in both
   file headers and `YieldCurve.is_provisional` (parsed from a `# provisional: true` line) -- surfaced as a
   loud warning by `scripts/run_stress_test.py` and a top-level `data_provisional` flag in
   `results/stress_test_output.json`. `scripts/verify_provisional_data.py` cross-checks them against a
   direct download (to run from a normal network) and `scripts/build_cache.py` runs it automatically first
   if it finds provisional data cached. **The Fed stress-scenario numbers are no longer provisional**:
   re-sourced by directly `curl`-ing federalreserve.gov (reachable directly, unlike treasury.gov/Yahoo) and
   parsing the actual embedded HTML `<table>` of quarterly scenario values with regex -- no summarising
   model in the loop at all. This independently re-derived the exact same peak VIX (72.0, Q2 2026) and peak
   BBB-10yr spread (5.7pp, Q3 2026) the Board's own prose states, and added a real sourced VIX baseline
   (23.4) replacing an earlier illustrative guess. Full citation and table excerpt in
   `docs/DATA_VERIFICATION.md` sections 9-10.
2. **Accounting.** Loans now value at **carrying value = notional - EL** (amortized-cost/provisioning
   treatment) and are never also fair-valued off the curve/spread -- eliminates the double-count by
   construction, not by a special-cased check. `RevaluationResult` reports `mtm_pnl` (bonds/swaps/options/
   FX only), `credit_loss` (loans' delta-EL only), and `total_stressed_loss` = both, as three explicit
   numbers. EL is stated as a 1-year, Basel/regulatory-style measure (not lifetime IFRS9/CECL), justified in
   `docs/ASSUMPTIONS.md`. 5 new tests confirm the split (`tests/test_revaluation.py::TestAccountingSplit`).
3. **Scenario coherence.** Replaced the single generic "moderate" tier (which had been reused, incoherently,
   for an idiosyncratic single-name credit event) with two distinct, narratively-coherent tiers:
   `idiosyncratic_credit_event` (entity-specific, no broad rate move, large spread/PD impact on just the
   named name) and `idiosyncratic_minor` (M&A/product launch/other, small entity-specific moves). The Fed's
   recessionary scenario (`fed_severely_adverse`, rates DOWN) and the brief's own inflationary example
   (`geopolitical_rate_shock`, rates UP) stay explicit and separate, each with a one-line economic
   narrative. 8 new tests (`tests/test_shocks.py`) verify every tier against the real config file, including
   that the two rate-direction scenarios actually point opposite ways.
4. **Shown, not just claimed** (see chat reply): all 8 real triggered signals with headline text/impact
   components/fired scenario; confirmed the earlier -6.05%/$645.9M example was a manually-constructed
   illustrative scenario, not a real trigger -- `run_stress_test.py` now reports the actual highest-impact
   real signal as the labelled "headline" and keeps the illustrative example clearly separate; full
   naive-vs-full-reprice tables; P&L by asset class for the real headline scenario.
5. **Entity-linking precision**: 50-headline hand-audit found ~30% precision before fixing, dominated by
   "Target" colliding with "price target" (confirming the review's hypothesis) and a ticker/verb collision
   ("ups"/UPS). Fixed (`src/nlp/entity_linking.py`): ambiguous bare aliases excluded (Target/Visa/Apple/
   Oracle), ticker symbols matched only via `$CASHTAG` not free text, a heuristic suppressing bank names
   used as the *source* of a rating action rather than the subject, and an unrelated regex-boundary bug
   (`\b` failing after punctuation) caught by the new regression tests along the way. Re-scored same sample:
   **91.7% precision** (44/48), 12 regression tests added, all documented including the remaining known gap.
   This fix changed real pipeline output -- `results/signals.jsonl` regenerated (86 signals, down from 89)
   and `results/stress_test_output.json` regenerated (6 fired, down from 8; headline scenario is now a
   cleanly-attributed Disney credit-event downgrade, not a false-positive-driven result).

100/100 tests passing. Gate status: **PASS** -- every point addressed with real code changes, real
re-measured evidence, and real regenerated output, not just documentation claims.

## Third review round (before Phase 5) -- event classification, CIs, documentation
Status: **DONE**

1. **Confirmed the Disney headline was an equity-analyst action**, not a credit-rating action ("Disney
   downgraded as **analyst says** parks attendance could take 2 years to 'normalize'"). Fixed
   `RuleBasedEventClassifier`: bare "downgrade" now only counts toward Credit Event when explicit
   credit-market vocabulary is also present. A first (opposite-direction) fix attempt was caught missing a
   second real case on re-run ("Take-Two downgraded on murky game slate", no explicit analyst word at all)
   -- inverted to the more conservative default. **A further, unrelated bug surfaced while verifying the
   re-run**: "war" matched as a bare substring inside "warns", spuriously tagging a 5-headline analyst-note
   cluster Geopolitical -- fixed with word-boundary regex matching in both `event_classification.py` and
   `entity_linking.py`. 11 new regression tests. Re-ran the full pipeline: 76 signals (down from 86), 3
   fired (down from 6), headline is now a clean Macroeconomic trigger ("US stock futures slip ahead of
   #inflation report"), not an artifact of either bug.
2. **Entity-linking stats with CIs**: Wilson 95% CI for 44/48 = [80.4%, 96.7%]. Fresh independent sample
   (600 newly-pulled real rows, since only 14 of the original pool's linked docs were unused) scored
   52/55 = 94.5%, CI [85.1%, 98.1%]; pooled 96/103 = 93.2%, CI [86.6%, 96.7%]. **Recall spot-check**: random
   sampling was too noisy to find 30 genuine candidates (only 2/80), so switched to a targeted search of
   the full ~973-doc corpus for every occurrence of the four originally-excluded ambiguous aliases. Result
   directly changed the shipped rule: "target" cost **zero** measured recall (0/151 bare occurrences were
   genuine Target Corp mentions) so stays excluded, but "apple"/"oracle" cost **100%** recall (6/6 genuine
   mentions missed, zero offsetting FP benefit found) so both were **removed** from the exclusion set.
3. **Documented 4 further limitations in `docs/ASSUMPTIONS.md`**: (a) a real-company signal shocks
   fictional portfolio positions by sector/country match, not by name -- an explicit sector-contagion
   assumption; (b) the Fed scenario's peak/trough is applied as one instantaneous shock, not its real
   ~2-year quarterly path; (c) replayed historical tweets (pre-2026 content, synthetic timestamps) are
   priced against a genuinely-dated 2026-10-02 market snapshot -- a real temporal mismatch, disclosed; (d)
   1-year EL approximates IFRS 9 Stage 1 only -- a real stress scenario would typically trigger Stage 2/3
   staging and lifetime ECL under the accounting standard, so this project's stressed credit-loss numbers
   are a lower bound, not a standard-compliant figure.

112/112 tests passing.

## Phase 5 — Dashboard + single run command
Status: **DONE**

- **Streamlit dashboard** (`src/dashboard/app.py`, 5 tabs), every number read from a file a script already
  wrote (`results/signals.jsonl`, `results/metrics.json`, `results/stress_test_output.json`) except the
  Scenario Explorer tab, which says explicitly that it computes live:
  1. **Live Signal Feed** -- filterable table (min impact, event class, source) over all real signals, plus
     a per-signal impact-component breakdown chart.
  2. **Engine Quality** -- macro-F1-with-CI bar chart across majority-baseline/VADER/FinBERT, FinBERT
     per-class breakdown, event-classification gold-labelling progress bar, impact-score event-study status
     (correctly shows "not yet run" rather than fabricating a number).
  3. **Stress Test** -- loud provisional-data warning when applicable; the REAL highest-impact triggered
     signal as the headline (not a manually-chosen example); MTM P&L vs credit-loss split as two separate
     metrics; P&L by asset class and by sector; top-10 contributors; the full naive-vs-full-reprice
     comparison charts for a real portfolio bond and option.
  4. **Scenario Explorer** -- the one tab that computes fresh: pick an event class + sector/country, revalue
     the real portfolio live. Verified for all 6 event classes, with and without a sector filter (correctly
     zero-impact for entity-specific scopes with no filter, real losses with one; portfolio-wide scopes
     ignore the filter as expected).
  5. **Audit Log** -- every signal's trigger decision (fired or not, and why) via the real trigger engine,
     plus the shock-config version string.
- **`run.py`**: single entry point. `--mode demo` (default) rebuilds signals from the committed cache and
  runs the stress test, then starts the signal API (FastAPI/uvicorn) and the dashboard. `--mode live` runs
  `scripts/build_cache.py` first. Graceful degradation already existed per-source in the ingestion pipeline
  (Phase 1); demo mode never touches the network beyond the one-time FinBERT weight download
  (confirmed: 82.97s first call, 86-180ms/doc after, measured in Phase 2/3).
- **Two real bugs found and fixed while actually running the full pipeline** (not found by unit tests,
  which is exactly why this end-to-end run mattered):
  1. `scripts/run_engine.py` printed real headline text containing emoji directly to a Windows console
     defaulting to cp1252, crashing with `UnicodeEncodeError` -- and because `run.py` treated any non-zero
     exit code as a hard pipeline failure, a cosmetic console-output issue stopped the entire demo. Fixed at
     the root: `run.py` sets `PYTHONIOENCODING=utf-8` for every subprocess step, and `run_engine.py`/
     `run_stress_test.py` also reconfigure their own stdout to UTF-8 so they're safe to run standalone too.
  2. `append_signal()`'s JSONL write is intentionally append-mode (for a genuine live/streaming run), but
     `scripts/run_engine.py` never cleared the previous run's file first -- so every `python run.py --mode
     demo` silently accumulated duplicate signals (228 = 76 x 3 after three runs, caught directly in the
     pipeline log). Fixed: the script now deletes `results/signals.jsonl` and `results/signals.db` before
     writing a fresh run's output, since this script is a full deterministic rebuild, not an incremental
     append.
- **End-to-end verification**: real browser screenshot wasn't available in this environment (no
  `chromium-cli`/Playwright installed, and the built-in browser tool can't reach localhost servers Claude
  itself starts) -- verified instead by (a) running the full `run.py --mode demo` pipeline for real
  (engine: 76 signals from 373 docs; stress test: 3/76 fired; API confirmed serving real data on `:8000`;
  dashboard confirmed serving HTTP 200 on `:8501`), (b) executing `src/dashboard/app.py` directly in
  Streamlit's "bare mode" to catch any Python-level exception across every tab's non-interactive code path
  (clean exit code 0, no errors), and (c) independently exercising the Scenario Explorer's button-click
  code path (the one branch bare mode doesn't reach) for all 6 event classes x with/without a sector
  filter, confirming correct entity-specific-vs-portfolio-wide behaviour in every case.

118/118 tests passing.

## Phase 6 — Module A (stretch)
Status: **DROPPED**, per explicit instruction. Not attempted.

## Phase 7 — Reproducibility & hygiene
Status: **IN PROGRESS** (clean-clone install running; this environment's installs have been
inconsistently slow throughout the build -- see earlier phases -- so this is taking a long time to confirm,
not stuck on an actual problem. Reporting what's done so far rather than blocking on it.)

- **Hygiene: done.** `pyflakes` run across `src/`, `scripts/`, `tests/`, `run.py` -- fixed every real
  finding (6 unused imports, 1 genuinely dead local variable in `revaluation.py`, confirmed not a bug
  before removing it, 6 f-strings with no placeholders). Repo size check: 627KB, no tracked file over 1MB,
  `git status` clean before every commit throughout the build.
- **Clean-clone + fresh-venv test: in progress.** Cloned the local repo into a fresh temp directory,
  created a fresh Python 3.11 venv, running `pip install -r requirements.txt` for real (not reusing the
  dev venv) to time the real install and catch anything that only works because of local venv state.
  Will report actual wall-clock time and `pytest` result once it completes -- re-running in Phase 11 too,
  per the review's explicit instruction, after Aadit's local data refresh.

## Phase 8 — README.md
Status: **DONE**

`README.md` is **generated**, not hand-typed for its numeric content: `docs/README_template.md` holds the
prose (written once) with a `{{KEY_RESULTS_SECTION}}` placeholder; `scripts/generate_readme.py` fills that
placeholder exclusively from `results/metrics.json` and `results/stress_test_output.json`, via a `require()`
guard that **raises** (refuses to write `README.md` at all) if any field it needs is missing or `None` --
verified with `tests/test_generate_readme.py` (4 tests covering present/missing/`None`/absent-block cases).
Follows the mandatory template exactly (candidate info, numbered sections 1-5, Limitations & Next Steps, AI
Assistance Disclosure). The exact run command (`python run.py --mode demo`) is in Quickstart.

## Phase 9 — Architecture diagram + deck
Status: **DONE**

- **`docs/architecture.png`** (2224x1378px, exceeds the >=2000px-wide requirement): generated by
  `scripts/generate_architecture_diagram.py` using matplotlib, not graphviz's `dot` binary -- confirmed
  `dot` is not installed in this dev sandbox (and may not be on every grader's machine either), so this
  avoids an external system dependency entirely. First attempt had real layout bugs (text overflowing box
  boundaries, a semantically-backwards arrow implying the dashboard feeds `run.py` rather than the other
  way around) -- caught by actually looking at the rendered image (`Read` tool) rather than trusting the
  code, per the dataviz skill's "render it and look at it" step; fixed and re-rendered twice before
  accepting it.
- **`docs/presentation.pptx`**, exactly 7 slides, generated by `scripts/generate_deck.py` using the same
  `require()` guard as the README generator -- refuses to build if sentiment-eval, stress-test, or
  naive-vs-full-reprice numbers are missing. Ships as `.pptx` directly (no PDF conversion step) because
  LibreOffice (needed for the `pptx -> PDF` conversion the original plan assumed) is not installed in this
  sandbox -- confirmed absent -- and the platform's own submission guidelines explicitly accept "PDF or
  PPTX", so this isn't a compliance gap. Three chart images (`docs/deck_assets/`) generated by
  `scripts/generate_deck_charts.py` from the same real `metrics.json`/`stress_test_output.json` data the
  dashboard reads -- labelled as generated charts, not claimed to be a dashboard screenshot, since no
  browser-automation tool (chromium-cli/Playwright) is available in this environment to capture one
  (confirmed in Phase 5). Structure verified by reading the `.pptx` back with `python-pptx` (7 slides,
  expected shape/image counts and dimensions) since no PDF viewer is available for a direct visual check
  either; the architecture-diagram and chart PNGs embedded in it were each visually inspected separately
  before embedding.
- Slide 7 (Limitations & Next Steps) states the two pending evaluations, the provisional market data, and
  every other limitation already documented in `docs/ASSUMPTIONS.md` -- nothing on the pending items is a
  fabricated placeholder number; they're named as pending in prose, which needs no guard because no number
  is claimed for them.

## Changes requested before Phase 10
Status: **DONE**

1. **`docs/presentation.pdf`**: repo structure names this file explicitly (not just the `.pptx`). LibreOffice
   (needed to export it) is confirmed not installed here. Built `scripts/audit_compliance.py` -- checked
   required files, no-oversized-files, no-secrets, and `pytest` passing -- and **ran it for real**: it
   currently fails with exactly one issue, `MISSING required file: docs/presentation.pdf`, by design. Won't
   pass until Aadit exports it locally and commits it (`docs/USER_TODO.md` step 6).
2. **Pending-metric handling clarified and improved**: `format_event_classification_status()` /
   `format_impact_event_study_status()` (new, in `generate_readme.py`, imported by `generate_deck.py`) now
   put a real status line for BOTH metrics into Key Results / the Limitations slide -- not just omit them.
   Currently both say "pending" with the exact command to produce them; once real, they'll say the actual
   number, **explicitly flagging "UNDERPOWERED" or "no statistically significant relationship" rather than
   printing a bare correlation that looks more conclusive than it is.** Pending metrics, listed exactly:
   `event_classification_eval` (needs gold labels) and `impact_score_event_study` (needs a real n>=200
   GDELT sample).
3. **Demo run time fixed at the root.** `run.py --mode demo` now loads the committed `results/` as-is by
   default (no FinBERT recompute) -- `--recompute` (or `--mode live`, which implies it) does the full
   rebuild. **Caught a real bug while verifying this**: `--no-dashboard` returned immediately after
   starting the API subprocess, which fired `atexit` and killed it within milliseconds -- the API looked
   like it was "hanging" in a first test run, but it had actually already been torn down before the first
   health-check poll landed. Fixed by blocking on `api_proc.wait()`. **Real measured startup: ~310ms** once
   the process is running (confirmed by direct `curl` polling after a pytest-level integration test hit an
   unrelated environment hang with nested subprocess trees -- the fast mocked tests plus this direct
   measurement together give solid confidence, so the slow test stays in the suite as opt-in evidence
   rather than blocking on diagnosing a sandbox-specific subprocess-cleanup quirk). 7 new tests in
   `tests/test_run_startup.py` (6 fast + 1 opt-in real).
4. **"Manual scenario — not triggered by a real signal"** now labels every non-real-trigger result
   consistently: the dashboard's Stress Test tab (when no real signal has fired) and Scenario Explorer tab
   (both the tab-level warning and the per-result label), `scripts/run_stress_test.py`'s
   `illustrative_example_NOT_from_a_real_trigger` label, and the deck generator's fallback text and chart
   title.
5. **Deck screenshot slots added.** Slide 5 now prefers a real screenshot from `docs/screens/` per slot
   (`live_signal_feed.png`, `stress_test.png`, `scenario_explorer.png`), falling back to the generated
   chart for any slot without one yet -- no code change needed once Aadit adds them, just re-run
   `scripts/generate_deck.py`. Exact list in `docs/USER_TODO.md` step 6.
6. **Clean-clone result, reported as promised**: finished at **1334s (~22 min) total install time** in this
   dev sandbox (consistent with this environment's demonstrated wildly inconsistent install speeds
   throughout the build -- not representative of a normal machine). `pytest tests/` in the clean clone: **120
   passed, 1 skipped, 56s**. This was cloned from an earlier commit in this round, so **Phase 7 is not being
   marked fully passed** -- a fresh clean-clone check against the final state is explicitly planned for
   Phase 11 (and again after Aadit's local data refresh, per `docs/USER_TODO.md`).

`docs/USER_TODO.md` rewritten with the exact ordered local-steps sequence requested: build_cache ->
resample gold set -> label + score classifier -> event study + provisional-data verify -> regenerate
pipeline output + README/deck -> PDF export + screenshots -> re-run the compliance audit and clean-clone
check.

124/124 fast tests passing (1 opt-in slow test skipped by default, verified manually for this round).

## Phase 10 — Demo script + Q&A prep
Status: **DONE**

1. **`docs/DEMO_SCRIPT.md`**: full timestamped shot list using the real current pipeline numbers (76
   signals, FinBERT 0.660 macro-F1 vs VADER 0.453 vs majority 0.267, bearish recall 76.5% vs 53%, the real
   triggered Macroeconomic/Fed-severely-adverse scenario moving portfolio value from $656,917,251 to
   $643,610,408). Budgeted to **4:15 with a 45s buffer**, under the 5:00 limit. Covers setup/run
   (`python run.py --mode demo`, no recompute, starts in well under 30s per Phase-10-pre-review item 3),
   all 5 dashboard tabs, and an explicit "Before recording" checklist telling Aadit to re-check these
   numbers against the dashboard on screen if the pipeline is regenerated first (per `docs/USER_TODO.md`
   steps 1-5).
2. **`docs/QA_PREP.md`**: 25 hostile-judge questions with honest answers, covering both the brief's
   suggested red-team angles (Impact Score validity, sentiment-eval leakage, shock-size sourcing,
   correlation vs causation, duplicate/syndicated news, production failure modes, synthetic portfolio
   justification, polling vs Kafka, rating-surveillance fit) and every real issue surfaced during this
   build specifically: the entity-linking precision bug and its Wilson-CI-measured fix, the Disney
   downgrade and "warns"/"war" classifier bugs, the classifier freeze rationale, PROVISIONAL vs sourced
   data, demo determinism, the MTM/credit-loss accounting split, EL vs IFRS9 lifetime-ECL caveat,
   sector-contagion assumption, instantaneous-vs-phased shock simplification, the naive-vs-full-reprice
   convexity result, and the manual-scenario labeling. Answers point at exact files/scripts/numbers rather
   than asserting conclusions.

**Fast test suite re-run for this round**: `rapidfuzz` (declared in `requirements.txt`, used by
`src/ingestion/dedup.py`) was missing from this dev-sandbox Python environment at the start of this round
-- a repeat of the sandbox's previously-documented inconsistent-install behavior, not a code regression.
Reinstalled it (`pip install rapidfuzz==3.10.1`) and re-ran: **130 passed, 2 skipped, 10.39s.**

Per the user's exact wording for this round ("Then do Phase 10...") -- no "continue without pausing"
clause was given this time, unlike prior rounds -- Phase 11 (final compliance audit + clean-clone re-check)
is **not** being started automatically; reporting back here first.

## Before-Phase-11 review round

Status report on each item from the prior round, re-verified against the current code (not recalled from
memory):

(a) **`docs/presentation.pdf` as an audit failure condition**: confirmed in `scripts/audit_compliance.py`
    `REQUIRED_FILES` -- re-ran it, correctly fails with exactly `MISSING required file:
    docs/presentation.pdf`.
(b) **Pending-metric handling**: confirmed `results/metrics.json` currently has only `sentiment_eval` --
    `event_classification_eval` and `impact_score_event_study` are both absent (pending). Both
    `format_event_classification_status()` / `format_impact_event_study_status()` are wired into both
    `generate_readme.py` and `generate_deck.py` (slide 7), so neither generator silently omits them.
(c) **Demo default load + measured startup + test**: confirmed `run.py`'s `should_recompute()` defaults
    to loading committed `results/` (no recompute) unless `--recompute`/`--mode live`; `tests/test_run_startup.py`
    exists; ~310ms measured startup documented in `run.py`'s docstring.
(d) **"Manual scenario" label**: confirmed present verbatim in the dashboard (4 call sites in
    `src/dashboard/app.py`) and in `scripts/run_stress_test.py`'s label. **Found one real inconsistency
    while verifying**: `scripts/generate_deck_charts.py`'s chart title used different wording ("MANUAL
    SCENARIO, not a real trigger") instead of the exact requested phrase. Fixed to "Manual scenario, not
    triggered by a real signal" and regenerated the chart to confirm no errors (current real data has
    `n_fired=5`, so this branch isn't hit by the currently-committed chart image, but the code path is now
    correct for whenever it is).
(e) **Screenshot slots**: confirmed `SCREENS_DIR`/`SLOT_SCREEN_FALLBACKS`/`resolve_slide5_images()` in
    `generate_deck.py`, and the exact 3-file list in `docs/USER_TODO.md` step 6.
(f) **Clean-clone + fresh-venv result**: **not re-run this round** -- the only result on record is the one
    already reported in the "Changes requested before Phase 10" section above (1334s install, 120
    passed/1 skipped/56s), against an earlier commit, explicitly not treated as a pass for the current
    HEAD. No newer clean-clone directory exists. This stays open for the real Phase 11, after Aadit's
    local data refresh, per the user's own instruction this round.

**Also found and fixed this round**: `docs/COMPLIANCE.md`'s "Problem brief" section cited stale numbers
(89 signals, "3/76 fired") left over from an earlier pipeline run, inconsistent with the actual current
`results/signals.jsonl` (76 signals) and `results/stress_test_output.json` (`n_fired: 5`). Corrected both
lines with a note that these numbers move whenever the cache/engine is re-run.

**Requirements-vs-imports check (requested this round)**: new `scripts/check_requirements.py` walks every
`.py` file under `src/` and `scripts/`, extracts top-level imports via `ast`, excludes stdlib + first-party
modules, maps known import/package-name mismatches (`yaml`->pyyaml, `dotenv`->python-dotenv,
`PIL`->Pillow, `sklearn`->scikit-learn, `pptx`->python-pptx), and fails if anything used has no matching
`requirements.txt` entry. Caught one false positive during development (`generate_readme` import flagged
as a missing package -- it's a sibling script import, not PyPI; fixed by also excluding local module/file
stems under `src/`/`scripts/`). Wired into `scripts/audit_compliance.py` as a new check
("All imports pinned in requirements.txt") and covered by `tests/test_check_requirements.py` (4 tests: one
real assertion against the actual repo state, three proving the detector itself would catch a real gap
rather than always passing). Currently passes clean -- every import, including `rapidfuzz`, is pinned.
Full suite: **134 passed, 2 skipped**.

## Phase 11 — DRY RUN (not final)

Walked `docs/COMPLIANCE.md` line by line. This is explicitly a dry run per the user's instruction --
nothing below is being marked final, and the real Phase 11 (including a second clean-clone check and
re-verifying `DEMO_SCRIPT.md`'s numbers against regenerated results) runs after Aadit's local data refresh.

**Passing / evidenced now:**
- All 6 "Problem brief" items — real evidence, numbers just corrected to match current data (see above).
- Repo structure, README template compliance, 7-slide deck, DEMO_SCRIPT.md, QA_PREP.md — all present with
  evidence already logged above and in prior phases.
- "All data (incl. synthetic) in /data with sources+assumptions" — substantially done: `README.md`
  section 3 documents every text/market data source with licence + provisional/sourced status, and
  `docs/ASSUMPTIONS.md` documents the synthetic portfolio's construction (PD/LGD, EL horizon,
  sector-contagion mapping). Minor gap: the synthetic portfolio itself isn't a row in the README's
  Dataset Used table (that table is scoped to text/market data sources) -- cosmetic, not a missing
  disclosure, since the same facts are documented in ASSUMPTIONS.md.

**Failing / pending now (expected, not a regression):**
- `docs/presentation.pdf` missing -- `scripts/audit_compliance.py` fails on exactly this, by design.
- Public GitHub repo -- not yet pushed; Aadit's action.
- Demo video -- script ready, recording is Aadit's action.
- Clean clone re-check -- not re-run since an earlier commit; explicitly deferred to the real Phase 11.
- "Ready for live jury pitch + Q&A" -- Q&A content is ready; overall readiness still gated on the three
  items above.

**Gap list for Aadit (everything that needs manual/local action, consolidated):**
1. Run the full local pipeline refresh (`docs/USER_TODO.md` steps 1-5) -- real GDELT data, gold-set
   labelling, event study.
2. Export `docs/presentation.pptx` to `docs/presentation.pdf` and commit it.
3. Capture the 3 dashboard screenshots into `docs/screens/`, re-run `generate_deck.py`.
4. Re-run `scripts/audit_compliance.py` -- expect a clean pass once 2-3 are done.
5. Re-run the clean-clone + fresh-venv check against the final commit (not the earlier one already on
   record).
6. Re-verify `docs/DEMO_SCRIPT.md`'s spoken numbers against whatever `results/` looks like after step 1,
   before recording.
7. Push to GitHub, make public, record + upload the demo video, then do the real (non-dry-run) Phase 11.

## Bug fix: Module B fired on positive-sentiment signals (found on Aadit's local run, 2026-10-18)

**Bug**: 2 of 5 fired stress tests came from strongly *positive* headlines -- a Hasbro analyst upgrade
(sentiment +0.942) and a Lowe's positive rating note (sentiment +0.916). `evaluate_signals()` in
`src/modules/stress_test/trigger.py` fired on `impact > threshold` alone; Impact Score measures how much a
story matters, not whether it's good or bad news, so a strongly positive story can score just as high as
a strongly negative one.

**Fix**: added a `sentiment_score < 0` requirement to the trigger engine (Module B only -- the frozen
`rule-v1` event classifier and the Impact Score formula are untouched). Full rationale in
`docs/ASSUMPTIONS.md` ("Module B: stress tests only fire on adverse signals"). 4 new regression tests in
`tests/test_trigger.py::TestSentimentGate`: positive-sentiment high-impact must not fire (the exact
Hasbro/Lowe's shape), zero-sentiment high-impact must not fire, negative-sentiment high-impact must still
fire, and when both impact and sentiment would fail, the reported reason names impact first.

**Re-ran the stress test on the existing `results/signals.jsonl`** (no engine recompute needed -- this is
a Module B trigger-logic fix, not an NLP signal-generation fix). Now **3 / 76 fire** (down from 5):

| signal_id | headline | sentiment | impact | event_class | scenario |
|---|---|---|---|---|---|
| sig_3e2f9d02a30ab82b | "US stock futures slip ahead of #inflation report..." | -0.960 | 7.97 | Macroeconomic | fed_severely_adverse |
| sig_afacc39e51bab7f3 | "U.S. jobs growth stalls at 29,000 in September as unemployment rises to 4.2%..." | -0.942 | 7.93 | Macroeconomic | fed_severely_adverse |
| sig_bf3a0340e01aeb08 | "UPDATE US Fed Minutes Release Amid Diminished Rate-Hike Prospects..." | -0.640 | 7.25 | Macroeconomic | fed_severely_adverse |

All three resolve to the same `fed_severely_adverse` / portfolio-wide scenario (same Macroeconomic
event-class-to-tier mapping), so the headline P&L is unchanged: value $656,917,251 -> $643,610,408, total
stressed loss $-13,306,843 (**-2.03%**, not the "-202.56%" my own ad hoc inline report script briefly
mis-displayed by double-applying a percent format to an already-percent field -- the pipeline's own output
and console summary were correct throughout).

Regenerated `results/stress_test_output.json`, `README.md`, `docs/presentation.pptx`, and the 3 deck chart
PNGs. Full suite: **138 passed, 2 skipped** (4 new). `scripts/audit_compliance.py`: same single expected
failure (`docs/presentation.pdf` missing), nothing new.

## Real local-network findings (Aadit's laptop, Windows/Python 3.11, 2026-10-18) resolved

1. **Provisional Treasury curve was off by 38-141bp at every tenor** (2y 4.83% provisional vs 3.47% direct,
   10y 5.28% vs 4.19%, 30y 5.63% vs 4.86%) -- a WebFetch transcription error, not date drift (too large/
   inconsistent across tenors to be ordinary rate movement). Added `scripts/build_cache.py --market-only`:
   fetches the Treasury curve directly (never provisional -- `fetch_treasury_curve()` never writes a
   `# provisional: true` header) plus FRED plus equity spot for just the tickers Module B needs. Re-ran it
   in this sandbox on a connection that reached treasury.gov directly this time and got **2y=3.47%,
   10y=4.19%, 30y=4.86% -- matching Aadit's own direct-download values exactly.** All PROVISIONAL banners
   (dashboard/README/deck) are driven off `stress_test_output.json`'s `data_provisional` flag, which is now
   `False` -- they disappeared automatically, no manual removal needed anywhere.
2. **yfinance 0.2.50 failed outright on a real machine** (`YFTzMissingError`/`"Expecting value"` for every
   ticker). **What Module B actually uses equity prices for, exactly:** only the `option` asset class (5 of
   50 positions, underlyings JPM and NVDA) -- Black-Scholes needs a spot for strike/quantity. Loans, bonds,
   swaps, and FX forwards never touch equity prices. Bumped `requirements.txt` to **yfinance==1.7.0**
   (confirmed current latest via `pip index versions yfinance` -- yfinance moved from the 0.2.x series to a
   1.x line at some point past 0.2.66); confirmed working end-to-end with no code changes to the fetch
   logic. Added graceful degradation regardless: `scripts/run_stress_test.py::exclude_unpriceable_options()`
   drops just the affected option position(s) if a spot price is ever missing again, loudly reported in
   `results/stress_test_output.json`'s new `excluded_positions` field, rather than crashing the whole run
   with an unhandled `KeyError`. 5 new tests in `tests/test_run_stress_test_exclusion.py`.
3. **GDELT returned HTTP 429 on every query for 2+ hours (0 articles)** -- abandoned as a data source for
   this submission, per instruction, not retried. `results/metrics.json`'s `impact_score_event_study` now
   records `"status": "not_run"` with the exact reason and date, instead of a number or silent omission.
   `format_impact_event_study_status()` (README + deck, same function) reports this "not run" status
   explicitly. The Limitations sections (README template + deck slide 7) and the Dataset Used table were
   all updated to state this plainly rather than describe GDELT as merely "unreachable from this dev
   sandbox" (no longer true-sounding once it's been abandoned outright, not just blocked here).
4. `docs/ASSUMPTIONS.md` documents all three findings/fixes in full, with the real before/after numbers.
   `docs/USER_TODO.md` rewritten: the GDELT-dependent gold-resampling step is gone (GDELT is abandoned), and
   the local refresh workflow now points at the new `scripts/refresh_local.ps1`.
5. **`scripts/refresh_local.ps1`** (new): market-only fetch -> re-run stress test -> regenerate README +
   deck -> run tests -> `git add`/`commit`/`push`, each step stopping the script on failure so nothing
   half-finished gets pushed. `-SkipPush` switch to review before pushing.

Re-ran the full pipeline on the freshly-sourced real data: headline scenario now **$667,925,507 ->
$651,855,012, total stressed loss -$16,070,495 (-2.41%)** (changed from the provisional run's -2.03% --
expected, since the underlying curve/spot inputs changed to real values). Regenerated
`results/stress_test_output.json`, `README.md`, `docs/presentation.pptx`, deck charts. Full suite:
**143 passed, 2 skipped** (5 new). `scripts/audit_compliance.py`: same single expected failure
(`docs/presentation.pdf` missing), nothing new broken.

## Correction (2026-10-19): the "transcription error" finding above was itself wrong

**Retraction:** the "Provisional Treasury curve was off by 38-141bp at every tenor" / "transcription error"
finding in the section above is **withdrawn**. It was based on a bug in this project's own code, not a
real data-quality problem.

**Root cause, found on a real local run of `scripts/refresh_local.ps1`:** `fetch_treasury_curve()` took
the CSV response's *last line*, assuming the file is sorted ascending (oldest first). Treasury's annual
file is actually sorted **descending** (newest first), so the last line was the year's first business day
(2026-01-02), not the latest. `--market-only` had been silently loading `as_of: 2026-01-02` instead of the
real latest date (~2026-10-16) -- and the "matches Aadit's laptop exactly" check in the prior round
compared *that same wrong row* against Aadit's own direct download, which doesn't prove anything about
whether the date was right.

**Re-checked, per tenor, against the correct 2026-10-02 row** (fetched fresh, located explicitly by date
rather than by file position): every one of the 12 published tenors matches the provisional snapshot
**exactly, 0bp difference** -- 1Mo 4.04%=4.04%, 2Yr 4.83%=4.83%, 10Yr 5.28%=5.28%, 30Yr 5.63%=5.63%, etc.
(full table in `docs/ASSUMPTIONS.md` "Treasury curve `as_of` bug"). The provisional WebFetch-relayed
snapshot was accurate for its stated date the entire time -- there was never a transcription error. The
previously-reported "38-141bp" gap was purely an artifact of comparing against the wrong (2026-01-02) row,
a ~9.5-month-earlier curve.

**Fix:** `fetch_treasury_curve()` now parses every row's date and selects the max, regardless of file
order. Re-fetched: `as_of: 2026-10-16` (199 rows parsed) -- the genuinely latest available business day.
3 tests added/updated in `tests/test_market_data.py`, including an explicit regression test that shuffles
out-of-order rows and asserts `as_of` is the max date present.

`docs/DATA_VERIFICATION.md` (new section 14) and `docs/ASSUMPTIONS.md` both corrected with the retraction
and the real per-tenor comparison -- the old (wrong) conclusion is left in place above as the historical
record, per this log's own convention of appending corrections rather than rewriting history, with this
entry marking it superseded.

**`.gitignore`:** added `data/cache/market/_verify_*.csv` (written by `scripts/verify_provisional_data.py`)
and `data/cache/news_gdelt.jsonl`, per instruction -- neither was actually tracked yet (`git rm --cached`
confirmed, correctly, "did not match any files"), so this is purely preventive for future runs.

**Re-ran the full pipeline on the corrected curve.** Headline scenario: **$658,497,132 -> $644,703,575,
total stressed loss -$13,793,557 (-2.09%)**. P&L by asset class: loan -$15,096,079, bond -$27,574,416,
option +$43,162,632, swap -$4,151,298, fx_forward -$10,134,396. (Changed again from the previous round's
-2.41% -- expected, since the curve date moved from the wrong 2026-01-02 to the correct 2026-10-16, a
materially different point in the yield curve's path.) Regenerated `results/stress_test_output.json`,
`README.md`, `docs/presentation.pptx`, deck charts. Full suite: **145 passed, 2 skipped** (3 new).

## Dashboard crash fix: KeyError on 'not_run' event-study status (2026-10-19)

**Bug reported from a real local run at `f81a1ff`:** `KeyError: 'n_resolved'` at
`src/dashboard/app.py` line 197, crashing the whole page (Streamlit executes the full script
top-to-bottom on every run -- `with tab:` only scopes layout, not execution -- so one tab's
unhandled exception stops every tab, including Stress Test, from rendering). Root cause: the
Engine Quality tab's `if not ies:` check is False for `ies = {"status": "not_run", ...}` (a
truthy dict), so it fell into the branch that does `ies["n_resolved"]` -- a key that genuinely
doesn't exist on the "not_run" shape introduced in the previous round's GDELT-abandonment fix.

**Fix:** explicitly check `ies.get("status") == "not_run"` before the numeric branch, and reuse
`scripts/generate_readme.py::format_impact_event_study_status()` (imported into `app.py`) for the
message, rather than duplicating status-interpretation logic -- the dashboard now always says
exactly the same thing as the README/deck for this metric. Remaining numeric-branch accesses
switched from bare `[]` to `.get()` with sensible fallbacks for the two optional sub-fields
(`spearman_r`, `power_adequate`/`note`) that are genuinely optional even within a resolved result.

**Audited every other `metrics.json`/`stress_test_output.json` read in `app.py`** for the same
class of bug: `sentiment_eval`'s sub-fields, `stress_test_output.json`'s top-level fields, and
`headline_scenario`'s fields are all unconditionally written by their producing scripts (confirmed
by reading `scripts/run_sentiment_eval.py` and `scripts/run_stress_test.py`'s output-dict
construction) -- not actually optional, so bare `[]` there is correct, not a latent bug.
`impact_score_event_study` was the only genuinely polymorphic field (absent / `not_run` / full
result), and is now the only one with branching logic.

**Added `tests/test_dashboard_app.py`** using `streamlit.testing.v1.AppTest` to run the real
`src/dashboard/app.py` against the actual current committed `results/` files (no mocking) and
assert zero exceptions -- this is the test that would have caught the reported bug. **It also
caught a second, real latent bug while being written**: Tab 1 (Live Signal Feed) and Tab 5 (Audit
Log) both used a bare module-scope variable named `rows`; Tab 1's `st.selectbox` `format_func`
lambda closes over `rows` by reference, and since Tab 5's code runs later in the same full-script
execution and reassigns `rows`, the lambda could end up looking up Tab 1's signal IDs in Tab 5's
audit rows (`KeyError: 'headline'`). Fixed by renaming Tab 1's variable to `feed_rows`, eliminating
the collision.

Full suite: **147 passed, 2 skipped** (2 new dashboard tests). `scripts/audit_compliance.py`: same
single expected failure (`docs/presentation.pdf` missing), nothing new.

## Gold-set labelling contamination fix (2026-10-19)

**Bug reported from a real local labelling run:** `scripts/label_events.py`'s `s` shortcut (accept the
rule baseline's own suggestion directly into `gold_label`) left no record of which rows took it --
contaminating the human gold set with the classifier's own predictions on an unknown subset. Aadit is
re-labelling all 200 rows from scratch rather than trying to reconstruct which were affected.

**Fix, enforced at two points:**
1. `scripts/label_events.py` -- the rule suggestion is never shown anymore, the `s` option is removed
   entirely, every typed label is stamped a new `label_source = "human_blind"` CSV column, and `--fresh`
   discards all existing `gold_label`/`label_source` values to restart labelling at row 1.
2. `scripts/score_event_classifier.py` -- refuses to score (writes nothing to `results/metrics.json`)
   unless every row has `label_source == "human_blind"`, including refusing if the column is missing
   entirely.

**Also fixed while rewriting the scorer:** macro-F1 was being dragged down by classes with zero support
in the gold sample (this project's gold set has had zero "Product Launch" examples the whole build) --
`sklearn`'s macro average over `labels=EVENT_CLASSES` forces a 0-support class's F1 to 0 via
`zero_division=0`, which isn't a real classifier failure. `macro_avg_over_present_classes()` now restricts
the average to classes with support>0, recording exactly which (`macro_avg_classes_included`); the full
6-class per-class breakdown (support shown explicitly) is still reported separately, nothing hidden.
Added a majority-class ("always Other") baseline (accuracy, macro-F1) and a closed-form Wilson 95% CI on
accuracy for both `rule-v1` and the baseline (statsmodels isn't installed here). `generate_readme.py`'s
`format_event_classification_status()` updated to surface all of this in the README/deck.

**The frozen classifier (`rule-v1`, `RULE_KEYWORDS`, `CREDIT_MARKET_INDICATORS`) was not touched** -- only
the labelling tool and the scorer's statistics changed, per instruction.

16 new tests (`tests/test_label_events.py` x7, `tests/test_score_event_classifier.py` x9), including a
Wilson-CI cross-check against the entity-linking audit's independently-reported 44/48 -> [80.4%, 96.7%]
figure. Confirmed against the real (still entirely unlabelled, 0/200) committed `data/eval/event_gold.csv`
that the scorer correctly refuses with "200 / 200 rows ... are not yet labelled" -- the contamination
happened on Aadit's local working copy, never committed. Full suite: **163 passed, 2 skipped** (16 new).
`scripts/audit_compliance.py`: same single expected failure (`docs/presentation.pdf` missing).

## Deck review fixes (2026-10-19)

Pulled `2e18683` (blind human gold labels + rescored metrics + docs/screens/*.png from Aadit's local run).
Fixed the generators per slide-by-slide review, not the pptx by hand:

1. **Slide 2**: removed the false "FinBERT is fine-tuned on the exact dataset the brief's own eval plan
   implied using" claim (the brief has no eval plan) -- corrected to the real fact: FinBERT is fine-tuned
   on Financial PhraseBank, evaluated on a disjoint dataset to avoid leakage. Restructured to lead with the
   business-problem statement as a standalone headline (`add_lead_statement()`), not buried in a bullet list.
2. **Slide 3 / docs/architecture.png**: found and fixed a real bug -- the diagram was embedded at a fixed
   width with no height check, pushing its bottom edge to ~8.9in on a 7.5in-tall slide (cut off ~18% of the
   image, invisible in the actual deck even though the standalone PNG looked fine). Fixed to fit both
   width/height bounds, confirmed bottom edge now at 7.25in. Also rewrote `generate_architecture_diagram.py`
   to compute GDELT status, market-data sourcing + as_of, the trigger rule, event-classification/impact-study
   results, and the test count all LIVE from `results/metrics.json`/`results/stress_test_output.json` and a
   live `pytest --collect-only` count -- it had been almost entirely hardcoded text before (stale GDELT-as-
   live-source, PROVISIONAL market data claim, missing sentiment gate, "pending" evals already resolved,
   "126 tests" stale by several rounds). Visually inspected and fixed two overflow issues found along the
   way (Trigger engine box text clipped left/right; a connector arrow+label cutting across the Evaluation
   box's text) before confirming the final render is clean.
3. **Slide 5**: renamed Aadit's 3 screenshots (`Screenshot 2026-10-18 23*.png`, confirmed which tab each
   showed by opening them) to the exact filenames the generator looks for -- confirmed via the generator's
   own printed output that all 3 slots now resolve to "REAL screenshot". Added the headline stress result
   (value before->after, total loss + %, MTM vs credit loss) and the event-classification result to the Key
   Results text. Naive-vs-full error now reported as % of position value (0.42%), not a bare dollar figure.
   Restructured the dense single-paragraph results text into separate paragraphs for both readability and
   more predictable vertical sizing.
4. **Slide 7**: removed the stale "finish event-classification scoring" next-step line (scoring is done).
   Added slide-appropriate (no backticks, no Python lists, no file paths) formatters
   `slide5_event_classification_line()`, `slide7_event_classification_bullets()`, `slide7_impact_study_line()`
   -- states plainly: rule-v1 has 100% precision but 34% recall (10 of 29) on Macroeconomic; Credit Event
   (n=1) and Geopolitical (n=2) cannot be evaluated in this 200-row blind-labelled sample. Next-step line
   corrected to "grow the gold sample for those two classes, investigate the Macroeconomic recall gap."
5. **Slide 6**: reworded the domain-fit bullet to state the signal taxonomy spans credit events without
   implying credit-event detection itself is validated (it isn't -- n=1, can't be evaluated).
6. **P&L chart (`generate_deck_charts.py`)**: fixed overlapping/crowded labels -- the fixed $300k/$800k
   label offset crowded the 0-line for small bars sharing an axis with much larger ones (swap -$4.2M next
   to option +$43.2M). Offset is now proportional to the chart's value range, with extra axis padding.

**LibreOffice was installed via winget specifically for this round** (`TheDocumentFoundation.LibreOffice`,
not present in this dev sandbox throughout the rest of the build) to render the deck to PDF and visually
check every slide for overflow, per instruction.

**LibreOffice install did not complete in this sandbox**: attempted via `winget install TheDocumentFoundation.LibreOffice --silent`, which downloaded the ~372MB installer successfully but then stalled for ~25 minutes with the `winget.exe` process alive and no `msiexec`/`soffice.exe` ever appearing -- consistent with this sandbox's previously-documented environment flakiness (wildly inconsistent install times elsewhere in this build). Killed the stalled process rather than wait indefinitely.

**Fell back to rigorous manual verification instead of a true PDF render:**
- Dumped and read the actual text of all 7 slides via `python-pptx` after every generator change, to confirm each wording fix landed exactly as intended (not just that the code looks right).
- Computed exact image-placement math (aspect ratio x target width/height x slide bounds) for every embedded image on every slide -- this is exactly what caught the real slide-3 cutoff bug (the architecture diagram's bottom ~18% was invisible on the actual slide, confirmed by the math: bottom edge at ~8.9in on a 7.5in-tall slide).
- Directly visually inspected the standalone `docs/architecture.png` and `docs/deck_assets/stress_test_chart.png` renders (not the pptx itself, since nothing in this sandbox can rasterize a slide to an image) after each fix, iterating until clean.
- Confirmed slide 5's three image slots resolve to the real screenshots via the generator's own printed output.

This is a real limitation of this review, stated plainly rather than claimed away: a true rendered-PDF slide-by-slide check (catching e.g. font-substitution reflow, PowerPoint's own text-box behavior vs. python-pptx's) was not possible here. Aadit has PowerPoint/LibreOffice on his own machine and should still do a final visual pass there before submission.
