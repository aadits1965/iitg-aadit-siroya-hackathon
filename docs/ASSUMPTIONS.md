# Assumptions Log

Every modelling/design assumption goes here with its justification and source (or "illustrative assumption,
no source"). Updated throughout the build, not just once.

## Methodology discipline

- **No metric, threshold, label mapping, or weight is ever tuned on an evaluation/validation split.**
  Any calibration (e.g. mapping FinBERT's 3-class output to a -1..1 score, choosing the impact-score trigger
  threshold, picking event-classification confidence cutoffs) is either (a) a fixed a-priori rule decided
  before looking at eval results, or (b) tuned only on a train split, never on the held-out validation/eval
  set used for reporting. This applies in particular to the sentiment evaluation in Phase 3, which scores
  against `zeroshot/twitter-financial-news-sentiment`'s validation split — that split is read-only for
  scoring. Reason: the user explicitly flagged this as a methodology requirement before Phase 1 began.

## Sentiment label mapping (Twitter Financial News Sentiment dataset)

- The dataset's integer labels are `0=Bearish, 1=Bullish, 2=Neutral` (confirmed via the dataset's own label
  scheme, see docs/DATA_VERIFICATION.md). This project's pipeline uses a continuous **-1..1** sentiment score
  (per the brief), not a 3-class label, so FinBERT's own `P(positive) - P(negative)` continuous score is used
  directly wherever possible.
- **Assumption, stated plainly:** when a discrete gold label is needed for scoring/comparison against the
  dataset's Bearish/Bullish/Neutral labels, the mapping used is `Bearish -> negative, Bullish -> positive,
  Neutral -> neutral`. This is a face-value mapping of financial-market-direction labels onto
  positive/negative/neutral sentiment polarity — "bearish" (expecting the stock to fall) is treated as
  negative sentiment about that stock, "bullish" as positive. This is a reasonable but not the only possible
  mapping (a Bearish tweet could in principle be written in a neutral or matter-of-fact tone); it is used
  because the dataset provides no finer-grained sentiment-polarity label, and it is documented here rather
  than silently assumed. Fixed before any evaluation numbers are produced, not adjusted afterward.

## Widened ticker universe for the event study only

`data/universe_event_study.csv` (80 tickers) is used **only** by `scripts/run_impact_event_study.py` for
entity-linking recall, to maximise the chance of resolving >=200 ticker-linked, timestamped GDELT headlines
within GDELT's query window — the correlation test needs that sample size for adequate statistical power
(see docs/EVALUATION.md section 3). It is a general list of large, frequently-covered US-listed companies
assembled for linking purposes, **not** claimed to be a current, authoritative index-constituents list, and
is never used for any index-membership claim. Module B and the main dashboard/engine continue to use the
curated 20-ticker `data/universe.csv`.

## Module B: shock library and credit assumptions

- **Sourced:** the "severe" shock tier in `config/scenarios.yaml` uses the Federal Reserve's published
  severely-adverse stress-test scenario magnitudes (equity -54%, rates -200bp, IG credit spread +440bp,
  VIX peak 72, house prices -29%, CRE -40%), fetched live 2026-10-04 — see docs/DATA_VERIFICATION.md
  section 9 for the citation and exact figures.
- **Illustrative, not sourced:** the "moderate" tier (40% of the severe tier's magnitudes) — the Fed
  publishes one severely-adverse scenario, not a graduated series, so this interpolation is this project's
  own choice, stated plainly rather than presented as a second official scenario.
- **Illustrative, not sourced:** high-yield credit-spread widening (the Fed document discusses BBB/IG
  spreads only, not HY separately); the VIX pre-stress baseline (18); the PD multiplier applied under
  stress (3.0x severe / 1.6x moderate / 1.3x geopolitical-example); and the "geopolitical_example" tier
  itself, which is the hackathon brief's own stated example (equities -10%, rates +200bp) kept deliberately
  separate from the Fed numbers because it moves rates in the opposite direction (inflationary/rate-shock
  shape vs. the Fed's recessionary/flight-to-quality shape) — blending the two would misrepresent both.
- **Illustrative, not sourced:** the rating-bucket-to-PD mapping and LGD-by-seniority values in
  `src/modules/stress_test/portfolio.py` (`RATING_TO_PD`, `LGD_SENIOR_SECURED/UNSECURED/SUBORDINATED`) are
  a monotonically-increasing-by-notch illustrative curve, not copied from a specific published agency
  table — stated in that module's own docstring and repeated here per the no-fabrication rule.
- **Simplification, stated in `src/modules/stress_test/pricing.py`:** the discount curve uses linear
  interpolation on par yields as a zero-rate proxy (no proper bootstrapping), and the interest-rate swap
  floating leg is priced via the standard par-reset simplification (PV(floating) = notional x (1 - DF(T))).
  Both are standard simplifications for a prototype of this scope, not full term-structure models.

## GDELT headline-level constraint

- The GDELT DOC 2.0 API returns `title` (headline) but no article body field. This project's NLP therefore
  operates on **headline-level text** for the GDELT news channel, not full article bodies. No article
  scraping is performed. Stated as a design constraint/limitation in the README and the deck, not hidden.
