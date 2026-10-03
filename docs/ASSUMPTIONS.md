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

## GDELT headline-level constraint

- The GDELT DOC 2.0 API returns `title` (headline) but no article body field. This project's NLP therefore
  operates on **headline-level text** for the GDELT news channel, not full article bodies. No article
  scraping is performed. Stated as a design constraint/limitation in the README and the deck, not hidden.
