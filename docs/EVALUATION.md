# Engine Evaluation (Phase 3)

Every number below is read from `results/metrics.json`, which is written only by the scripts named in
each section. Nothing here is typed in by hand.

## 1. Sentiment: FinBERT vs VADER baseline

**Run for real** against the held-out validation split of `zeroshot/twitter-financial-news-sentiment`
(2,000 of 2,388 examples; MIT licensed). This split is confirmed disjoint from FinBERT's own fine-tuning
data (Financial PhraseBank — see docs/DATA_VERIFICATION.md), so this is a genuine out-of-sample test, not
leakage. No threshold, label mapping, or weight was tuned on this split (see docs/ASSUMPTIONS.md).

| Model   | Accuracy | 95% CI (bootstrap, n=2000) | Macro-F1 | 95% CI            | Latency/doc |
|---------|----------|------------------------|----------|---------------------|-------------|
| VADER (naive baseline) | 0.505 | [0.483, 0.526] | 0.453 | [0.429, 0.476] | 0.11ms |
| FinBERT (primary)      | **0.722** | [0.702, 0.742] | **0.660** | [0.635, 0.684] | 135ms |

FinBERT's 95% CI does not overlap VADER's on either metric — the improvement over the naive lexicon
baseline is real, not noise. FinBERT is ~1,200x slower per document on CPU (135ms vs 0.11ms), which is the
expected cost of a transformer vs a lexicon; still well within the throughput this project needs (a few
hundred cached docs per demo run, not a high-frequency feed).

Reproduce: `python scripts/run_sentiment_eval.py`.

## 2. Event classification: rule baseline vs zero-shot

**Status: pending.** The gold label set (`data/eval/event_gold.csv`) has 110 real rows sampled from the
373 genuinely-ingested documents (Mastodon live posts + replay tweets; see Phase 1), stratified by the rule
baseline's own guess, but needs Aadit's hand labelling before per-class precision/recall/F1 and a confusion
matrix can be reported (`docs/USER_TODO.md`). Reporting the rule baseline's own suggestions as if they were
gold labels would be circular, so no number is reported here yet. The zero-shot classifier
(`facebook/bart-large-mnli`) is implemented but its CPU latency has not yet been benchmarked at scale —
deferred to the same run that scores against the finished gold set, since both need to happen together
to be worth the model's one-time ~1.6GB download.

## 3. Impact Score validation (event study)

**Status: blocked on this development machine, not fabricated.** The event-study methodology (Phase 3.3)
needs real, timestamped news headlines linked to tickers — the tweet-replay dataset has no timestamps
(confirmed) so the brief's own instruction was to use GDELT instead. GDELT (and several other market-data
hosts: Yahoo Finance, the US Treasury yield-curve CSV endpoint) are confirmed unreachable from this
development sandbox's shared egress IP (HTTP 429 persistently from GDELT across a full ~17-minute live run,
HTTP 000/connection-failure from Treasury, JSON-decode failures from yfinance — see
docs/DATA_VERIFICATION.md section 8). This is an environment-specific network restriction, not a defect in
GDELT or in the study design.

What **is** verified:
- `src/eval/impact_event_study.py` implements the full method: no-look-ahead date alignment (the first
  trading day whose entire session starts after the event timestamp), abnormal return = stock return − SPY
  return, Spearman correlation with bootstrap 95% CI, mean |AR| by impact decile.
- `tests/test_impact_event_study.py` (4/4 passing) verifies this mechanically against known, hand-constructed
  price series: a +10% stock move against a flat SPY on a known date is correctly recovered as a +10%
  abnormal return, and the date-alignment logic is checked both for an event before market open (same-day
  close used) and after market close (next day's close used).
- Only **4 real, non-synthetic-timestamp, ticker-linked documents** exist in this environment so far (from
  the live Mastodon pull). The script refuses to report a Spearman correlation below
  `MIN_SAMPLE_FOR_CORRELATION = 30` — reporting a correlation on n=4 would be noise presented as signal, so
  no number is produced rather than a misleading one.

**Next step (Aadit, see docs/USER_TODO.md):** once `scripts/build_cache.py` is run from a normal network to
populate `data/cache/news_gdelt.jsonl`, run `python scripts/run_impact_event_study.py` to produce the real
result. If the correlation turns out weak or absent even with a real sample, the Impact Score will be
re-framed everywhere (README, deck, QA prep) as a transparent rule-based severity score rather than an
empirically-validated predictor — exactly as the build plan requires.
