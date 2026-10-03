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

### Early start on Phase 4 (while waiting on background jobs)
Not yet reported as a phase completion, but already built and tested while Phase 3's background jobs ran:
`src/modules/stress_test/curve.py` (yield curve + shock application; uses a clearly-labelled illustrative
fallback curve since the Treasury endpoint is also blocked here) and `pricing.py` (bond full-cashflow
pricing, swap DV01, Black-Scholes options, expected loss), with 14 hand-checkable unit tests passing
(zero-coupon bond vs closed form, DV01 sign for payer/receiver swaps, put-vs-spot monotonicity, EL
monotonicity in PD). Portfolio generator (`portfolio.py`) also drafted, not yet tested. This will continue
once Phase 3 is reviewed.
