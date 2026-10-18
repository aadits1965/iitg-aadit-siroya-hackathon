# Assumptions Log

Every modelling/design assumption goes here with its justification and source (or "illustrative assumption,
no source"). Updated throughout the build, not just once.

## Event classifier: frozen at rule-v1

The **rule-based classifier** (`RuleBasedEventClassifier`, `src/nlp/event_classification.py`) is the one
that ships as the production classifier (`src/nlp/engine.py`'s default) -- fast, transparent, zero extra
model cost, and already debugged against real signal output (the analyst-vs-credit-event and "war"/"warns"
fixes in docs/DATA_VERIFICATION.md section 12). The zero-shot NLI classifier remains implemented and
available as a comparison method for Phase 3 evaluation, but is **not** the production classifier.

**Frozen as `RULE_CLASSIFIER_VERSION = "rule-v1"`, git tag `classifier-v1`.** Once Aadit finishes hand-
labelling `data/eval/event_gold.csv`, `scripts/score_event_classifier.py` scores this exact frozen version
once and the result is recorded in `results/metrics.json` tagged `rule-v1`. **Any later change to
`RULE_KEYWORDS`, `CREDIT_MARKET_INDICATORS`, or the classify() logic is a new version** (`rule-v2`, its own
git tag) and must never be tuned or re-scored against the same gold set `rule-v1` was evaluated on --
that would be exactly the eval-set-tuning this project's own rules forbid (see the no-tuning-on-eval-split
rule below). A `rule-v2` needs either a fresh gold sample or an explicitly train/test-split portion of the
existing one, decided before looking at v2's results on it.

## Gold-set contamination found and fixed (2026-10-19): the 's' shortcut

**Found on a real local labelling run:** an earlier version of `scripts/label_events.py` showed the rule
baseline's own suggestion on every row and offered `s` to accept it directly into `gold_label`, with no
column recording which rows took that shortcut. Any row labelled via `s` is the classifier's own
prediction, not an independent human judgement -- scoring `rule-v1` against a gold set partly made of
`rule-v1`'s own guesses is circular for those rows, and there was no way to tell afterward which rows were
affected. Aadit is re-labelling all 200 rows from scratch rather than trying to reconstruct which were
contaminated.

**Fix, enforced at two points so this can't recur silently:**
1. `scripts/label_events.py` -- the rule suggestion is never shown, the `s` option is removed entirely
   (not just discouraged), and every label actually typed is stamped `label_source = "human_blind"` in a
   new CSV column. `--fresh` discards all existing `gold_label`/`label_source` values and restarts at row
   1, for exactly this re-labelling.
2. `scripts/score_event_classifier.py` -- **refuses to score** (exits non-zero, writes nothing to
   `results/metrics.json`) unless every row has `label_source == "human_blind"`, including refusing
   outright if the column doesn't exist at all (the exact shape of the file before this fix).

**Also fixed while rewriting the scorer: macro-F1 was being dragged down by classes absent from the gold
sample.** `sklearn.classification_report`'s macro average, given `labels=EVENT_CLASSES`, averages in
every one of those six classes even when a class has **zero support** in `y_true` -- its F1 is forced to
0 by `zero_division=0`, which isn't a real classifier failure, just a class this particular 200-row sample
happens not to contain (this project's gold set has had zero "Product Launch" examples the entire build).
`macro_avg_over_present_classes()` now restricts the macro average to classes with support>0 in the gold
set, and records exactly which classes were included (`macro_avg_classes_included`) so this is never
silently different from what a reader would expect "macro-F1" to mean. The full per-class breakdown
(all six classes, support shown explicitly, including 0) is still reported separately -- nothing is
hidden, only the *average* excludes absent classes.

**Also added:** a majority-class ("always Other") baseline, scored the same way (accuracy, macro-F1 over
present classes), plus a closed-form Wilson 95% CI on accuracy for both `rule-v1` and the baseline
(statsmodels isn't installed here, same reasoning as the entity-linking audit in
`docs/DATA_VERIFICATION.md` section 13) -- so `rule-v1`'s eventual score has a real floor to be judged
against, not just a bare number. 16 new tests across `tests/test_label_events.py` (7) and
`tests/test_score_event_classifier.py` (9).

**The frozen classifier itself (`rule-v1`, `RULE_KEYWORDS`, `CREDIT_MARKET_INDICATORS`) was not touched**
by any of this -- only the labelling tool and the scoring script's statistics changed.

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

## Module B: four further limitations (added after second review round)

### (a) Mapping a real-company signal onto fictional counterparties (sector/rating contagion)

The NLP engine identifies real companies (e.g. a Disney credit downgrade, ticker DIS). The stress-test
portfolio's counterparties are all fictional (rule 5/§8-9 forbids real client data). So when a real signal
fires an `entity_specific` shock, **no synthetic position IS the named real company** — instead, the shock
is applied to every fictional position that shares the real company's **sector** (and/or country) —
`ShockSet.applies_to()` in `src/modules/stress_test/shocks.py` matches on `position.sector`/`position.country`,
never on name. This is an explicit **sector-contagion assumption**: "a credit event at one named real
company is treated as informative about credit risk for other, unrelated fictional names in the same
sector," not a claim that any fictional position has a demonstrated correlation to the real company. It is
a reasonable, standard risk-management shortcut (sector/rating-bucket contagion is a real phenomenon credit
desks do model) but is not calibrated to any specific correlation estimate here — stated as a modelling
choice, not a sourced number.

### (b) Fed scenario peak/trough applied as an instantaneous shock, not the quarterly path

The real Federal Reserve severely-adverse scenario (docs/DATA_VERIFICATION.md section 10) unfolds
**gradually over ~2 years** — e.g. the 10-year Treasury yield declines from 4.3% (Q4 2025 jump-off) to its
2.3% trough only by Q4 2026, and the VIX's 72.0 peak is a single Q2-2026 quarter within a longer path that
starts at 58.8 (Q1 2026) and recedes afterward (table in section 10). `config/scenarios.yaml`'s
`fed_severely_adverse` tier takes the **peak/trough magnitude** from that path (-200bp, VIX 72, etc.) and
applies it as a **single instantaneous before/after shock** in one revaluation, not as a multi-quarter
trajectory. This means the dashboard's "before vs after" view shows the scenario's worst point reached
immediately, compressing roughly two years of the Fed's own designed path into one step. A full
implementation would revalue the portfolio at each quarter along the path and show the trajectory of
losses, not just the trough — explicitly out of scope here, stated as a simplification rather than
presented as a faithful reproduction of the Fed's time-phased scenario.

### (c) Replayed historical tweets priced against a 2026-10-02 market snapshot

The signals that trigger Module B come substantially from `zeroshot/twitter-financial-news-sentiment`
(the offline replay source — see docs/DATA_VERIFICATION.md section 1), whose underlying tweets are
historical (content references like "predicting 2020 will be 'a return to solid growth'" and coronavirus-era
headlines place the real collection period well before this project's 2026 setting). These are replayed with
a **synthetic ingestion-time timestamp** (`raw_meta.timestamp_is_synthetic = true`, documented since Phase 1),
not their true original publish date. The portfolio they trigger a stress test against is priced off a
genuinely dated **2026-10-02** Treasury curve and equity snapshot. **The result is a temporal mismatch**: a
stress test "triggered" by old replayed headline content is revalued against current market data, so the
demo is not a coherent single point-in-time snapshot of "what these real headlines imply for markets today."
This is fine, and disclosed, for demonstrating the *mechanism* end-to-end (ingestion to signal to trigger to
revaluation) but must never be described as a real-time or historically-faithful market read — the README/
deck/QA prep state this plainly rather than let a demo audience assume otherwise.

### (d) 1-year EL vs IFRS 9 staging under stress

Building on the EL-horizon note below: this project's EL is a flat **1-year** PD x LGD x EAD applied
uniformly, which approximates an **IFRS 9 Stage 1** treatment (performing exposures, 12-month expected
credit loss). A real severely-adverse stress scenario is, by its own definition, exactly the kind of event
that would typically trigger a **"significant increase in credit risk"** under IFRS 9, moving affected
exposures to **Stage 2** (or Stage 3 for exposures that actually default), which requires **lifetime ECL**,
not 12-month EL — a materially larger figure for any exposure with remaining maturity beyond one year (up
to 7 years in this portfolio). **This project's stressed credit-loss numbers (`credit_loss` in
`RevaluationResult`) should therefore be read as a lower bound relative to what an IFRS 9-compliant stage
migration would produce**, not as a full accounting-standard-compliant credit loss estimate. Implementing
proper staging (a significant-increase-in-credit-risk trigger + a lifetime-PD curve) is out of scope for
this prototype and is named here as a limitation, not silently approximated as if it were already handled.

## Module B: EL horizon and the MTM / credit-loss split

- **EL horizon: 1-year, not lifetime.** `RATING_TO_PD` in `src/modules/stress_test/portfolio.py` is an
  illustrative **1-year** PD curve, applied directly regardless of a loan's remaining maturity (1-7 years in
  this portfolio). This is the Basel/regulatory-capital convention (point-in-time, 1-year EL), not an
  IFRS9/CECL-style lifetime expected credit loss (which would require multiplying by remaining maturity or
  a cumulative default curve, and would typically only apply once a loan has migrated to a worse "stage").
  Justification: this project is a stress-test/risk-signal prototype in the Basel/capital-stress tradition
  (closer in spirit to the Fed's own CCAR/DFAST framework, which this project's shock magnitudes are drawn
  from), not a financial-statement loss-provisioning exercise, so the simpler, standard 1-year EL is used
  uniformly. Stated as a simplification, not claimed to match any specific bank's actual IFRS9/CECL model.
- **MTM vs credit-loss split (no double counting):** a loan's stress impact flows through exactly ONE
  channel -- `src/modules/stress_test/revaluation.py` values a loan at **carrying value = notional - EL**
  (amortized-cost / provisioning treatment, the standard banking-book accounting for held loans) and does
  **not** separately reprice it off the yield curve or a credit spread. Bonds, swaps, options and FX
  forwards are the opposite: fully fair-valued (full cashflow discounting / closed-form pricing) and a
  credit-spread shock shows up there as a price decline -- this is the standard trading/AFS-book treatment,
  and those instruments do **not** also get a separate EL-based credit-loss line, since the spread-driven
  price move already reflects the market's updated credit view. Reported as two explicit numbers:
  `mtm_pnl` (bonds+swaps+options+FX only) and `credit_loss` (loans' delta-EL only), summing to
  `total_stressed_loss` -- never merged into a single unlabelled figure. Verified by
  `tests/test_revaluation.py::TestAccountingSplit` (5 tests), including a direct check that a loan's value
  is completely unchanged under a rate+spread shock with no PD multiplier (i.e. the curve/spread genuinely
  has zero effect on loan valuation, by construction, not just by coincidence in one test case).

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

## Module B: stress tests only fire on adverse signals (sentiment < 0)

**Bug found on a real local run (2026-10-18):** 2 of the 5 fired stress tests came from strongly
*positive* headlines -- a Hasbro analyst upgrade (sentiment +0.942) and a Lowe's positive rating note
(sentiment +0.916). Both had high Impact Scores and fired purely on `impact > threshold` in
`src/modules/stress_test/trigger.py`'s `evaluate_signals()`.

**Root cause:** Impact Score (`src/nlp/engine.py`'s impact component) measures how much a story matters --
sentiment *magnitude*, source breadth, entity importance, novelty -- not whether the news is good or bad.
A strongly positive upgrade moves the needle on "this matters" exactly as much as a downgrade of the same
magnitude would. The frozen event classifier (`rule-v1`) is a separate, intentionally untouched component
(see "Event classifier: frozen at rule-v1" above) and was not the source of this bug -- it correctly
classified these as non-credit events; the trigger engine simply never checked sentiment direction before
this fix.

**Fix:** `evaluate_signals()` now requires `sentiment_score < 0` in addition to `impact > threshold` before
a signal can fire. This is a Module B trigger-engine rule, not a change to the frozen classifier or the
Impact Score formula -- a stress test models *losses*, so it has no meaning for a signal whose sentiment
is non-negative, regardless of how high its Impact Score is. `sentiment_score == 0` (neutral) also does
not fire, by the same logic -- a stress test needs a reason to expect a loss, and neutral sentiment gives
none.

**Regression tests:** `tests/test_trigger.py::TestSentimentGate` -- a positive-sentiment, high-impact
signal must not fire (the exact Hasbro/Lowe's shape); a zero-sentiment, high-impact signal must not fire;
a negative-sentiment, high-impact signal must still fire; and when both impact and sentiment would fail,
the reported reason names impact first (checked in that order).

## Treasury curve `as_of` bug: picked the year's FIRST row, not the latest (2026-10-19)

**This section corrects an earlier, wrong conclusion in this same log.** A previous entry here claimed the
provisional Treasury curve (fetched via WebFetch) was off by 38-141bp at every tenor against a direct
download and called that a "transcription error." That comparison was itself wrong, and the conclusion is
retracted -- see below.

**Root cause:** `fetch_treasury_curve()` took `lines[-1]` of the annual CSV response on the assumption the
file is sorted ascending (oldest first). It is actually sorted **descending** (newest first) -- so
`lines[-1]` was the **year's first business day** (2026-01-02), not the latest. The first `--market-only`
run in this build silently loaded the 2026-01-02 curve and reported `as_of: 2026-01-02` -- a stale date
that went unnoticed at the time, and the "matches Aadit's laptop exactly" check that followed was
comparing that same wrong (01-02) row against Aadit's own direct download, which happened to also be an
early-year rate level -- not evidence the fetch was dated correctly.

**What this means for the earlier "transcription error" claim, checked directly, per tenor:** fetched the
raw Treasury CSV again and compared the provisional snapshot's stated date (2026-10-02) against the
**direct fetch's own 2026-10-02 row** (not the 2026-01-02 row used by mistake before):

| Tenor | Provisional (stated 2026-10-02) | Direct fetch's actual 2026-10-02 row | Diff |
|---|---|---|---|
| 1 Mo | 4.04% | 4.04% | 0bp |
| 2 Mo | 4.11% | 4.11% | 0bp |
| 3 Mo | 4.19% | 4.19% | 0bp |
| 6 Mo | 4.27% | 4.27% | 0bp |
| 1 Yr | 4.46% | 4.46% | 0bp |
| 2 Yr | 4.83% | 4.83% | 0bp |
| 3 Yr | 4.96% | 4.96% | 0bp |
| 5 Yr | 5.06% | 5.06% | 0bp |
| 7 Yr | 5.17% | 5.17% | 0bp |
| 10 Yr | 5.28% | 5.28% | 0bp |
| 20 Yr | 5.67% | 5.67% | 0bp |
| 30 Yr | 5.63% | 5.63% | 0bp |

**Every tenor matches exactly.** The provisional 2026-10-02 snapshot was correct for its stated date all
along -- there was never a transcription error. The earlier "38-141bp" gap was entirely an artifact of
comparing it against the wrong row (2026-01-02, ~9.5 months earlier) due to the `as_of`-selection bug
above, not a data-quality problem with the WebFetch-relayed snapshot. `docs/DATA_VERIFICATION.md` section 9
is corrected accordingly -- it no longer claims a transcription error.

For reference, the real two-week rate move (2026-10-02 -> 2026-10-16, the genuinely latest row) is a
modest, plausible curve move -- short end up ~6-8bp, long end down ~17-20bp (a mild flattening) -- nothing
like the original mis-measured gap.

**Fix:** `fetch_treasury_curve()` now parses every data row's date and picks the **max**, regardless of
file order, instead of assuming a sort order. 3 new/updated tests in `tests/test_market_data.py`,
including one that explicitly shuffles out-of-order rows and asserts `as_of` is the max date present, not
whichever row happens to be last in the file. Re-fetched after the fix: `as_of: 2026-10-16` (199 rows
parsed), matching the expected "most recent business day" directly.

**Separately, still true:** `scripts/build_cache.py --market-only` fetches the curve directly (no
summarising model in the loop), which never writes a `# provisional: true` header, so
`YieldCurve.is_provisional` is `False` for any curve fetched this way -- this part of the original fix was
correct and unaffected by the `as_of` bug. All PROVISIONAL banners (dashboard, README, deck) are driven off
`stress_test_output.json`'s `data_provisional` flag and disappear automatically once a real curve is in
place, regardless of which date it is.

## Module B: equity prices are optional except for options

**Exactly what in Module B uses equity spot prices:** only the `option` asset class (5 of 50 positions in
the real portfolio, underlyings JPM and NVDA -- see `data/synthetic/portfolio.csv`). Black-Scholes needs a
spot price to derive the strike (`moneyness * spot`) and the position's quantity (`notional / spot`) --
see `value_position()` in `src/modules/stress_test/revaluation.py`. **Loans, bonds, swaps, and FX forwards
never touch `equity_spot`** -- loans are priced off PD/LGD/EAD only, bonds and swaps off the discount
curve only, FX forwards off a flat percentage move. So Module B does *not* need the ~80-ticker
event-study-universe equity pull at all (that pull exists only for the now-abandoned impact-score event
study) -- it needs real spot prices for exactly 2 tickers.

**yfinance 0.2.50 (the version this project was originally pinned to) failed outright on a real machine**
(`YFTzMissingError` / `"Expecting value"` JSON errors, for every ticker) on 2026-10-18. Bumped to **1.7.0**
(confirmed the current latest release via `pip index versions yfinance`; yfinance moved from the 0.2.x
series to a 1.x line at some point after 0.2.66) -- confirmed working end-to-end against the existing
`fetch_equity_prices()` code with no code changes needed.

**Graceful degradation, in case yfinance ever fails again on a given machine:** rather than letting a
missing spot price crash the entire stress test with an unhandled `KeyError`, `scripts/run_stress_test.py`'s
`exclude_unpriceable_options()` drops just the affected option position(s) and records them, loudly, in
`results/stress_test_output.json`'s `excluded_positions` field (position ID, underlying, notional, reason)
-- never silently. The other 45+ positions (and any option whose underlying *does* have a spot price) still
price normally. See `tests/test_run_stress_test_exclusion.py`.

## Impact-score event study: not run

**GDELT returned HTTP 429 on every query for 2+ hours (0 articles returned)** on a real local run,
2026-10-18. Per instruction, GDELT is **abandoned as a data source for this submission** -- not retried,
not substituted with another source without saying so. `results/metrics.json`'s
`impact_score_event_study` key records `"status": "not_run"` with the exact reason and the date attempted,
rather than either omitting the key (which would look unexamined) or computing a number from whatever
non-GDELT data happens to be cached (which would silently change what the number means). The event study's
own code (`src/eval/impact_event_study.py`, `scripts/run_impact_event_study.py`) is unaffected and
unchanged -- it is built and mechanically verified (synthetic-price-series tests pass), it simply has no
real sample to run against. The README's Key Results section, Limitations section, and the deck's slide 7
all report this exact "not run" status via `scripts/generate_readme.py::format_impact_event_study_status()`
-- no invented correlation number appears anywhere.

## Deck review fixes (2026-10-19): a false claim, a slide-level image cutoff, and stale generators

**Found on Aadit's slide-by-slide review of `docs/presentation.pptx`:**

1. **False claim, slide 2:** "FinBERT is fine-tuned on the exact dataset the brief's own eval plan implied
   using (leakage)" -- the brief has no eval plan, so this was simply wrong, not an exaggeration of a real
   finding. Corrected to the real, already-verified fact: FinBERT is fine-tuned on Financial PhraseBank, so
   this project evaluated it on a disjoint dataset specifically to avoid leakage (see the sentiment-eval
   leakage check elsewhere in this build). Slide 2 also restructured to lead with the business-problem
   statement as a standalone headline, not buried as bullet one among process bullets.
2. **Real bug, slide 3: the architecture diagram was cut off at the bottom of the slide itself**, not just
   within the standalone PNG. `docs/architecture.png` is a wide image (aspect ratio ~1.61); embedding it at
   a fixed `width=12.5in` with no height constraint let its height grow to ~7.75in, starting at `top=1.15in`
   -- pushing its bottom edge to ~8.9in on a 7.5in-tall slide. The bottom ~18% of the diagram was invisible
   in the actual deck the whole time; this was never visible by looking at the standalone PNG in isolation,
   only by checking how it's placed on the slide. Fixed in `scripts/generate_deck.py` to fit BOTH the width
   and height bounds (whichever constrains first), centered horizontally -- confirmed the embedded picture's
   bottom edge is now at 7.25in, inside the 7.5in slide.
3. **`docs/architecture.png` itself was almost entirely hardcoded text**, not read from
   `results/metrics.json`/`results/stress_test_output.json` -- it still showed GDELT as a live source (long
   abandoned), market data as PROVISIONAL (long since replaced with a direct fetch), the trigger rule
   without the sentiment gate added days earlier, event classification as "pending" (already scored), the
   impact study as "pending GDELT" (already recorded "not run"), and a hardcoded "126 tests" count stale by
   several rounds of new tests. Rewritten to compute all of these live from the real files plus a live
   `pytest --collect-only` count, exactly the discipline `generate_readme.py`/`generate_deck.py` already
   follow for every other number in this project.
4. **Overlapping chart labels, slide 5's P&L chart:** `scripts/generate_deck_charts.py` placed each bar's
   dollar label a FIXED $300k/$800k above/below the bar's tip -- fine when all bars are similar magnitude,
   but this chart has asset classes from -$4.2M (swap) to +$43.2M (option) sharing one axis, so the fixed
   offset crowded the 0-line for the small bars. Offset is now a fraction of the chart's actual value range,
   with extra axis padding so the largest-magnitude labels never clip the plot edges either.
5. **Naive-vs-full reprice error reported as a bare dollar figure**, which doesn't say whether the error is
   material. Slide 5 now reports it as a percentage of the position's own (true, full-reprice) value at that
   shock -- e.g. "0.42% of position value" rather than a dollar amount with no reference point.
6. **Slide 7 had gone stale**: a "finish event-classification scoring" next-step line that no longer
   applied (scoring is done -- Aadit's blind-labelled gold set was scored in the previous round) and the
   eval-status text reused `generate_readme.py`'s Markdown-oriented formatters verbatim, which include
   backticks and a literal Python list (`['Geopolitical', 'Macroeconomic', ...]`) -- fine in a Markdown
   README, wrong on a slide. Added `slide5_event_classification_line()`, `slide7_event_classification_bullets()`,
   and `slide7_impact_study_line()` in `generate_deck.py` -- slide-appropriate plain language, computed from
   the same `results/metrics.json`, stating plainly: rule-v1 has 100% precision but only 34% recall (10 of
   29) on Macroeconomic, and Credit Event (n=1) / Geopolitical (n=2) cannot be evaluated yet in this
   200-row blind-labelled sample. Next-step line corrected to reflect this: grow the gold sample for those
   two classes and investigate the Macroeconomic recall gap, not "finish labelling."
7. **Slide 6 implied credit-event detection without the caveat** that it isn't actually evaluable yet
   (n=1 for Credit Event, see above). Reworded to state the domain fit (the signal taxonomy spans credit
   events) without claiming the detection itself is validated.
8. **The three screenshots Aadit captured** (`docs/screens/Screenshot 2026-10-18 23*.png`) didn't match the
   exact filenames `scripts/generate_deck.py`'s `SLOT_SCREEN_FALLBACKS` looks for -- confirmed which tab
   each one showed by opening them, then renamed to `live_signal_feed.png`/`stress_test.png`/
   `scenario_explorer.png`. Re-ran the generator and confirmed via its own printed output that all three
   slots now resolve to "REAL screenshot", not the generated-chart fallback.

**LibreOffice** was not installed in this dev sandbox throughout this build (confirmed repeatedly); it was
installed via `winget` for this round specifically to render the deck to PDF and visually check every slide
for overflow -- see PROGRESS.md for the result.

## Second deck review round (2026-10-19): LibreOffice render on a real machine

Aadit rendered `e656ad8` with LibreOffice on his own machine (the install in this sandbox never completed,
see above) and found further real issues a layout-math check alone couldn't catch:

1. **Slide 5's three dashboard screenshots were unreadable at deck scale** -- real UI chrome (filter
   controls, column headers) shrinks to illegible text at ~4in wide, a limitation of using literal
   screenshots rather than purpose-built charts. Replaced with two large (6in-wide) generated charts
   (sentiment macro-F1 with CI error bars; P&L by asset class for the headline scenario) plus one callout
   panel stating the headline result at a glance: total stressed loss, split into MTM and credit loss, each
   signed (`+`/`-`) so the two components' relationship to the total is unambiguous at a glance rather than
   requiring the reader to infer signs from unsigned dollar figures. Bullet text cut to 3 short lines.
2. **The event classifier's accuracy was never shown next to its baseline anywhere it appeared** (slides 5,
   7, README) -- 88.5% reads as unconditionally good until you know the "always predict 'Other'" baseline
   already gets 84.0% for free. Added `event_classifier_stat()` in `generate_readme.py` (a single canonical
   stat string: accuracy vs. baseline, Macroeconomic precision/recall) and used it everywhere -- README,
   slide 5, slide 7 -- so this comparison is never missing and never phrased three different ways.
3. **Slide 2's "collided with 'price target' in nearly every analyst note" was a vague, unmeasured claim**
   standing in for a real, already-measured finding. Replaced with the actual numbers from the
   entity-linking audit: 30% precision (18/61) before the fix, 91.7% (44/48) after on the same sample,
   confirmed 94.5% (52/55) on an independent fresh sample -- see "Event classifier: frozen at rule-v1"
   section's sibling finding in `docs/DATA_VERIFICATION.md` sections 11 and 13.
4. **A file path and a test filename were still on slide 4** (`tests/test_demo_idempotency.py`) despite the
   no-backticks/no-paths rule applied to slides 5 and 7 the previous round -- the rule hadn't been checked
   against every slide, only the two that had just been edited. Grepped the full generator for any
   remaining path-like string in slide text (not docstrings/print statements) and removed the two found
   (this one, and a `docs/USER_TODO.md` reference in slide 5's provisional-data warning).
5. **Visual polish**: body font raised to >=18pt everywhere (was as low as 11.5pt on the old slide 5, 13pt
   on slide 7); bullets shortened throughout; slides 2, 6, and 7 restructured into two columns (plus, on 6,
   a real-number callout panel) instead of a single flat bullet list, using the lower half of the slide
   that was previously empty. Title slide's text is now two EXPLICIT lines ("AI/NLP Risk Engine" /
   "+ Strategic Portfolio Stress Test") rather than one long string left to PowerPoint's own word-wrap,
   which risked leaving a single word stranded alone on its own line depending on exact font-rendering
   metrics this environment can't reproduce without LibreOffice.
6. Removed the now-dead screenshot-slot mechanism (`SLOT_SCREEN_FALLBACKS`, `resolve_slide5_images()`) from
   `generate_deck.py` entirely, rather than leaving it as unused code now that slide 5 no longer uses
   screenshots -- `docs/USER_TODO.md` updated to say the three captured screenshots are no longer read by
   anything.

## GDELT headline-level constraint

- The GDELT DOC 2.0 API returns `title` (headline) but no article body field. This project's NLP therefore
  operates on **headline-level text** for the GDELT news channel, not full article bodies. No article
  scraping is performed. Stated as a design constraint/limitation in the README and the deck, not hidden.
