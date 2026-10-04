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
