# Engine Evaluation (Phase 3)

Every number below is read from `results/metrics.json`, which is written only by the scripts named in
each section. Nothing here is typed in by hand.

## 1. Sentiment: FinBERT vs VADER vs majority-class baseline

**Run for real** against the held-out validation split of `zeroshot/twitter-financial-news-sentiment`
(2,000 of 2,388 examples; MIT licensed). This split is confirmed disjoint from FinBERT's own fine-tuning
data (Financial PhraseBank — see docs/DATA_VERIFICATION.md), so this is a genuine out-of-sample test, not
leakage. No threshold, label mapping, or weight was tuned on this split (see docs/ASSUMPTIONS.md) — the one
exception, by convention not violation, is the majority-class baseline reading the label distribution,
since it has no parameters to fit.

**Label distribution (class-imbalanced):** negative 289 (14.5%), positive 373 (18.6%), neutral 1338 (66.9%).

**Macro-F1 is the headline metric, not accuracy** — the distribution above shows why: a model that always
predicts "neutral" gets 66.9% accuracy for doing *nothing*, which would look deceptively strong on accuracy
alone.

| Model | Macro-F1 | 95% CI | Accuracy | 95% CI | Negative (bearish) recall | Latency/doc |
|---|---|---|---|---|---|---|
| Majority-class ("always neutral") | 0.267 | [0.262, 0.272] | 0.669 | [0.648, 0.690] | **0.000** | ~0ms |
| VADER (lexicon baseline) | 0.453 | [0.429, 0.476] | 0.505 | [0.483, 0.526] | 0.529 | 0.11ms |
| **FinBERT (primary)** | **0.660** | **[0.635, 0.684]** | 0.722 | [0.702, 0.742] | **0.765** | 138.5ms |

The majority baseline's accuracy (66.9%) is actually *higher* than VADER's (50.5%) despite being a
do-nothing baseline — exactly the distortion macro-F1 is meant to catch: it scores 0.267 because it has
zero recall on both the negative and positive classes. FinBERT's macro-F1 95% CI does not overlap either
baseline's — the improvement is real, not noise. For a risk engine, bearish recall matters most (missing a
genuine negative signal is the costlier error): FinBERT catches 76.5% of real bearish examples, well above
VADER's 52.9% and the majority baseline's 0%. FinBERT is ~1,200x slower per document than VADER on CPU
(138.5ms vs 0.11ms) — the expected cost of a transformer vs a lexicon, still well within what this project
needs (a few hundred cached docs per demo run, not a high-frequency feed). Full per-class precision/recall/F1
for every model is in `results/metrics.json`.

Reproduce: `python scripts/run_sentiment_eval.py`.

## 2. Event classification: rule baseline vs zero-shot

**Status: pending.** The gold label set (`data/eval/event_gold.csv`) has 110 real rows sampled from the
373 genuinely-ingested documents (Mastodon live posts + replay tweets; see Phase 1), stratified by the rule
baseline's own guess, but needs Aadit's hand labelling before per-class precision/recall/F1 and a confusion
matrix can be reported. Reporting the rule baseline's own suggestions as if they were
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
docs/DATA_VERIFICATION.md sections 8-9). This is an environment-specific network restriction, not a defect
in GDELT or in the study design. (An AI-assisted web-fetch tool *could* reach Treasury and Yahoo Finance
through a different network path and was used to seed a single real dated snapshot for Module B — see
section 9 of DATA_VERIFICATION.md — but that same tool got the same GDELT 429, so this route can't solve
the news side.)

**Sample-size threshold, and why it's 200, not an arbitrary round number:** detecting a modest correlation
(r≈0.2 — a plausible effect size for a single rule-based severity score against noisy daily abnormal
returns) at ~80% power with a two-sided alpha=0.05 test needs n≈194 (standard Fisher z-transform sample-size
formula for a correlation test). `MIN_SAMPLE_FOR_POWER = 200` in `src/eval/impact_event_study.py` reflects
that, not a guess. Below that, the script **still computes and reports** the Spearman r, its bootstrap 95%
CI, and the mean-|AR|-by-decile table (never suppressed), but flags `power_adequate: false` and adds an
explicit "UNDERPOWERED" note — e.g. at n=30 the 95% CI around an observed r=0.2 is roughly [-0.17, 0.52],
wide enough to be uninformative, so the CI (not the point estimate) is always what should be reported.

What **is** verified:
- `src/eval/impact_event_study.py` implements the full method: no-look-ahead date alignment (the first
  trading day whose entire session starts after the event timestamp), abnormal return = stock return − SPY
  return, Spearman correlation with bootstrap 95% CI, mean |AR| by impact decile.
- `tests/test_impact_event_study.py` (5/5 passing) verifies this mechanically against known, hand-constructed
  price series: a +10% stock move against a flat SPY on a known date is correctly recovered as a +10%
  abnormal return, date alignment is checked both before and after market close, and the underpowered-flag
  behaviour is checked explicitly (a number is reported with n=5, correctly flagged `power_adequate=False`).
- Only **4 real, non-synthetic-timestamp, ticker-linked documents** exist in this environment so far (from
  the live Mastodon pull) — n=4 is below even the n>=3 floor needed to compute a correlation at all in one
  of the four cases tested, so no number can be produced here regardless of the power threshold.
- **Widened universe for the event study only:** `data/universe_event_study.csv` (80 tickers) feeds a
  separate, wider GDELT pull (`scripts/sample_event_gold.py`'s sibling, `ingest_gdelt_event_study()` in
  `src/ingestion/pipeline.py`) specifically to get this sample size up — the core 20-ticker universe used by
  the dashboard/Module B is kept separate and unchanged (see docs/ASSUMPTIONS.md).

**Next step:** run `scripts/build_cache.py` from a normal
network, then `scripts/run_impact_event_study.py`. If n stays below 200 even with the widened universe and
18-month GDELT window, or if the correlation turns out weak/absent at adequate power, the Impact Score will
be re-framed everywhere (README, deck, QA prep) as a transparent rule-based severity score rather than an
empirically-validated predictor — exactly as the build plan requires, and the underpowered/null result
itself is reported, not hidden or re-run until a better number appears.
