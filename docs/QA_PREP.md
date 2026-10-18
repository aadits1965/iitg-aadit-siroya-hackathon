# Q&A Prep — Red-Teaming This Project as a Hostile S&P/Crisil Judge

Honest answers, not deflections. Where the honest answer is "this is a real limitation," it says so —
that's the point of this document.

## Core methodology

**1. Why should I believe the Impact Score means anything?**
Right now, you shouldn't fully — the event-study validation (Spearman correlation between Impact Score
and realised abnormal returns) was never run. GDELT, the news source it needed for a large enough
timestamped, ticker-linked sample, returned HTTP 429 on every query for 2+ hours (0 articles) on a real
attempt and has been abandoned as a data source for this submission — this isn't a hypothetical gap, it's
a confirmed dead end with this source. The methodology itself is implemented and mechanically verified
(hand-built price series, no-look-ahead date alignment; see `docs/EVALUATION.md` section 3), but until a
real result exists, the Impact Score should be read as a **transparent, documented rule-based severity
score** — every component is visible — not an empirically-validated predictor.

**2. Is there leakage in the sentiment evaluation?**
Checked specifically: FinBERT is fine-tuned on Financial PhraseBank (confirmed from its model card). The
evaluation here uses a *different* dataset (`zeroshot/twitter-financial-news-sentiment`'s validation
split), confirmed disjoint from FinBERT's training data. No threshold or label mapping was tuned on that
split either.

**3. Why these shock sizes? Source?**
The "severe" tier is the Federal Reserve's own 2026 severely-adverse stress-test scenario, fetched
directly from federalreserve.gov (not a summary — the raw HTML table was parsed) and cited exactly. Every
other tier (moderate/idiosyncratic/geopolitical) is explicitly labelled an illustrative assumption, not a
second sourced figure — see `config/scenarios.yaml`'s header and `docs/ASSUMPTIONS.md`.

**4. Correlation vs causation in the event study?**
The event study, once it runs on real data, measures association (Spearman correlation between Impact
Score and |abnormal return|), never claims causation. Confounders — earnings dates, market-wide days,
multiple news items per ticker per day — are explicitly named as uncontrolled-for in both the code
docstring and `docs/EVALUATION.md`.

**5. How would you handle duplicate/syndicated news?**
Exact normalised-title hashing plus fuzzy matching (rapidfuzz, 88% token-sort-ratio threshold) within a
48-hour window — tested with 9 passing dedup tests. Real measured effect: Mastodon ingestion deduped 81
fetched posts down to 73.

## Data and scope

**6. Why is the portfolio synthetic, and are the suggested transaction datasets actually wholesale?**
No — the brief's suggested datasets (Salad Money, Kaggle "Financial Transactions") are retail card/spending
data, not loans/bonds/derivatives. They can't define a wholesale banking portfolio, so I generated a
documented synthetic one instead (50 positions, 5 asset classes, fictional counterparties, fixed seed) and
said so explicitly rather than forcing a mismatched dataset in.

**7. Why polling instead of Kafka/a real message bus?**
Scope and honesty — a flat JSONL file plus a FastAPI endpoint is "polling-based pub/sub," documented as
such everywhere it's mentioned, never dressed up as a real streaming architecture.

**8. How would this connect to real rating-surveillance workflows?**
The signal schema (sentiment/event/impact + full traceability back to source documents) is the natural
hook point — a surveillance analyst's queue could subscribe to `GET /signals?min_impact=7` the same way
Module B's trigger engine does. Not built further than that in this prototype.

**9. What breaks in production (latency, rate limits, adversarial/fake news)?**
FinBERT inference (~86-138ms/doc measured) is fine at this scale but wouldn't hold at high-frequency-feed
volume without batching/GPU. GDELT's rate limit is a confirmed, not hypothetical, problem: a real attempt
returned HTTP 429 on every query for over 2 hours straight (0 articles) — this project's own news
ingestion hit exactly the production failure mode this question is asking about. No adversarial-text
defences are implemented; a coordinated fake-headline campaign would be scored at face value.

**10. Why is NLP headline-level only for GDELT, not full article text?**
Confirmed live: GDELT DOC 2.0's JSON response has no article-body field, only title/url/seendate/domain
metadata. Scraping full article bodies wasn't done — that would mean fetching and redistributing
third-party publisher content beyond what GDELT's own CC0 metadata licence covers.

## Things that were specifically broken and fixed (expect follow-ups on any of these)

**11. I heard entity linking had precision problems — what happened?**
A 50-headline manual audit found ~30% precision, dominated by the word "Target" (alias for Target Corp)
matching the generic financial phrase "price target" in nearly every analyst note. Fixed by excluding
ambiguous bare-word aliases, matching tickers only via `$CASHTAG`, and a heuristic suppressing a bank's
own name when it's acting as the *source* of a rating action ("X downgraded... at JPMorgan") rather than
the subject. Re-measured at 91.7% (Wilson 95% CI [80.4%, 96.7%]) on that sample, and 94.5% (CI [85.1%,
98.1%]) on a second, independent 50-headline sample pulled later. A targeted recall check then found
"Target" cost **zero** measured recall (every one of 151 bare occurrences was the generic phrase, not the
retailer) but "Apple"/"Oracle" cost **100%** recall (every genuine mention was missed) — so those two were
un-excluded based on that evidence. Documented gap: a bank name with no adjacent verb at the very end of a
headline still slips through sometimes.

**12. The event classifier mislabelled things too?**
Yes — "Disney downgraded as analyst says parks attendance could take 2 years to normalize" was tagged
Credit Event at 0.99 confidence purely because "downgrade" matched a keyword, when it's plainly an
equity-analyst stock-rating opinion, not a credit-rating action. Fixed: bare "downgrade" only counts
toward Credit Event when genuine credit-market vocabulary (Moody's, S&P, "bond", "credit rating", etc.) is
also present. A related bug found by the same process: "war" matched as a bare substring inside "warns",
spuriously tagging several "<analyst> warns on <company>" headlines Geopolitical — fixed with
word-boundary regex matching everywhere, not just that one case.

**13. Is the event classifier still being tuned?**
No — it's frozen (`rule-v1`, git tag `classifier-v1`) specifically so the eventual score against the
hand-labelled gold set is honest. `scripts/score_event_classifier.py` refuses to run until labelling is
complete, and any future rule change becomes `rule-v2`, scored separately, never re-tuned against the same
gold rows `rule-v1` was judged on.

**14. What's "provisional" market data — and what actually happened with it?**
Market data is **not** provisional anymore — the Treasury curve and equity spot prices are fetched
directly (`scripts/build_cache.py --market-only`), as of 2026-10-16. But the path to get there is worth
knowing, because it's a real example of catching my own mistake rather than a clean story: an earlier
WebFetch-relayed snapshot (summarising model in the loop, used only because this dev sandbox's direct
network calls failed) was later compared against a direct fetch and looked wrong by 38-141bp at every
tenor — I called that a "transcription error" and wrote it up as one. It wasn't. The actual bug was in my
*own* curve-parsing code: it took the last row of Treasury's annual CSV assuming the file is sorted
ascending by date; the file is actually sorted descending (newest first), so "last row" was the *year's
first business day*, not the latest — I was comparing the provisional snapshot's October date against a
January row by accident. Re-checked per tenor against the *correct* date: the original provisional
snapshot matched exactly, 0bp difference, every tenor. The provisional data was never wrong. I was.
Fixed the parser to pick the max date regardless of file order, added a regression test with deliberately
shuffled rows, and left the wrong conclusion in `docs/ASSUMPTIONS.md`/`docs/DATA_VERIFICATION.md` as a
visible retraction rather than quietly editing it out. The Fed stress-scenario numbers were never affected
by any of this — those were separately sourced via a direct `curl` to federalreserve.gov.

**15. Does demo mode actually reproduce the same result every time?**
Yes, verified directly: ran the real engine (real FinBERT) twice end-to-end and diffed
`results/signals.jsonl` byte-for-byte — identical. This required a real fix: signal timestamps were
originally wall-clock `now()`, which made reproducibility impossible by construction; changed to derive
from the underlying document's own timestamp.

## Accounting and finance-specific

**16. Walk me through why MTM P&L and credit loss are reported separately.**
A loan in this model has exactly one channel for stress impact: its carrying value is `notional - EL`
(PD × LGD × EAD, amortized-cost/provisioning treatment) — it's never *also* repriced off the yield curve
or a credit spread. Bonds/swaps/options/FX are the opposite: fully fair-valued, and a credit-spread shock
shows up there as a price move. Reporting them as one undifferentiated number would either double-count a
credit event's impact on a bond (both a spread-driven price drop AND a separate EL hit) or hide a loan's
credit deterioration inside a vague blended figure.

**17. Is this EL a real accounting-standard figure?**
No — it's a flat 1-year PD × LGD × EAD (Basel/regulatory-capital style, closer to IFRS 9 Stage 1). A real
severely-adverse scenario would typically trigger a "significant increase in credit risk" under IFRS 9,
moving exposures to Stage 2/3 and requiring *lifetime* ECL — a materially larger number for any position
with remaining maturity beyond a year. This project's stressed credit-loss figures should be read as a
lower bound, stated as such in `docs/ASSUMPTIONS.md`, not a standard-compliant estimate.

**18. How does a real-company signal affect a synthetic portfolio with no real counterparties?**
By sector/country match, not name match — an explicit, documented contagion assumption. A Disney credit
event shocks the fictional portfolio's Communication Services-sector positions, not anything literally
named Disney (there is none). This is a standard risk-desk shortcut (sector/rating-bucket contagion is
real), but it's not calibrated to any specific correlation estimate — stated as a modelling choice.

**19. Why does the shock apply instantly instead of over time?**
The Fed's real scenario unfolds over ~2 years (10-year Treasury doesn't reach its 2.3% trough until Q4
2026, VIX peaks mid-scenario then recedes). This project applies the peak/trough magnitude as a single
instantaneous before/after shock, compressing that path into one step — a real simplification, not a
faithful reproduction of the time-phased scenario.

**20. The naive-vs-full-reprice comparison — is the gap real or an artifact?**
Real: both methods are implemented properly (full cashflow discounting / closed-form Black-Scholes vs.
genuine first-order duration/delta approximations), and the error grows monotonically with shock size in
testing (confirmed by `tests/test_naive_approx.py`) — that's convexity/gamma, not a coincidence of two
versions of the same shortcut.

## Demo-specific (anticipate if a manual scenario is shown)

**21. Is this scenario you just ran a real alert, or did you pick it?**
If it's the Scenario Explorer: manually picked, and labelled "Manual scenario — not triggered by a real
signal" in the dashboard and deck specifically so this is never ambiguous. Checked directly: as of this
writing, zero real signals in the cached data are both Geopolitical and above the impact threshold, so
showing that particular scenario live requires the manual path.

**22. Why is there no real Geopolitical trigger in the data?**
Checked directly: exactly one Geopolitical-classified signal exists in the 76-signal corpus, at impact 6.35
(below the 7.0 threshold) and sentiment +0.10 (also fails the sentiment-negative gate — it wouldn't fire
even at a lower impact threshold). The current cache is Mastodon live-posts and a replayed historical-tweet
dataset — genuinely Geopolitical, high-impact, bad-news stories are rare in that mix. With GDELT now
abandoned as a data source for this submission (see Q1/Q9), there's no further step expected to surface
one — this is the corpus the demo has to work with.

## Broader honesty checks

**23. What's the single thing most likely to be wrong in this submission?**
The Impact Score's predictive validity — it's the one claim in the whole pipeline resting on an evaluation
that couldn't be completed in this environment. Everything else (sentiment accuracy, entity-linking
precision, pricing correctness, demo determinism) has a real, measured number behind it.

**24. Why Mastodon instead of Twitter/X for social data?**
Checked directly: X's free tier in 2026 has no read access at all (pay-per-use, ~$0.005/read). Mastodon's
public hashtag timelines work with no auth and carry real timestamps — confirmed live before committing to
it, not assumed.

**25. If I gave you one more day, what would you do?**
Not retry GDELT — it's a confirmed dead end for this submission, not a transient issue. I'd spend the day on
a different news source for the impact-score event study (the one evaluation that's genuinely stuck), and
on expanding the gold-labelling sample specifically for Credit Event and Geopolitical, which currently have
1 and 2 examples respectively — nowhere near enough to say anything about how the classifier performs on
them.

## The headline stress result, walked through in detail

**26. Why does "US stock futures slip ahead of #inflation report" trigger a full Fed severely-adverse
scenario? That headline doesn't sound severe.**
Because the mapping is by event *class*, not by headline severity — this signal classified as
Macroeconomic (impact 7.97, sentiment -0.96), and in `config/scenarios.yaml`, Macroeconomic maps to the
`fed_severely_adverse` tier, portfolio-wide. That's a real, documented design choice, not a bug: this
project doesn't have a graduated set of macro scenarios of different severities, only the one sourced
Fed scenario plus illustrative lighter tiers for *other* event classes (idiosyncratic, geopolitical). Any
Macroeconomic-classified signal that clears the impact and sentiment gates fires the same severe scenario,
regardless of how severe the specific headline sounds in isolation. The honest critique: a single
inflation-report headline probably shouldn't carry the same weight as, say, a confirmed recession
announcement — a real production version would need graduated macro severity tiers, which this prototype
doesn't have.

**27. Walk me through the P&L: why do bonds lose $27.6M when the scenario pushes Treasury yields DOWN?
Why do options gain $43.2M — what positions are those?**
Bonds lose despite falling rates because of *credit spreads*, not the base curve. The Fed scenario applies
two things at once to corporate bonds: the Treasury curve falls 200bp (`rate_parallel_bp: -200`), but
investment-grade credit spreads widen 440bp (`credit_spread_widening_bp.investment_grade`) — and bonds in
this model discount at curve-rate-plus-spread (`src/modules/stress_test/pricing.py::bond_price()`). Net:
a roughly 240bp *increase* in the effective discount rate despite the lower base curve, so bond prices
fall. The rate decrease alone would have helped; the spread widening dominates it.
Options gain because all 5 option positions in the portfolio are **puts** on JPM and NVDA
(`data/synthetic/portfolio.csv`), and the scenario is a 54% equity crash (`equity_pct_move: -0.54`) plus a
VIX spike (baseline 23.4 → peak 72, roughly 3x implied vol). A deep-in-the-money put, revalued at much
lower spot and much higher implied volatility, is worth dramatically more — that's the real mechanism, not
an error. (There are no calls in this portfolio, so every option position benefits from the same crash
that hurts the equity-linked credit exposure elsewhere.)

## Event classification: the real numbers, and what I'd change

**28. The event classifier is 88.5% accurate versus an 84.0% always-'Other' baseline, and only catches 34%
of true Macroeconomic headlines. Why ship it at all? What would you actually change?**
I'd ship it with that number stated plainly, which is what this submission does — not because 88.5% vs
84.0% is a strong result (it barely beats guessing the majority class), but because the alternative is
shipping *nothing* measurable, or quietly tuning the rule on this exact gold set until the number looks
better, which this project's own rules explicitly forbid (the classifier is frozen as `rule-v1` specifically
so this score is honest). The real information is in the per-class breakdown, not the headline accuracy:
100% precision on Macroeconomic means it's never *wrong* when it calls one, but 34% recall means it misses
two out of three real ones — it's a conservative, high-precision/low-recall rule set, which for a
downstream trigger engine (fires a stress test) is a defensible default (false positives are more costly
than missed triggers here) but a real limitation for anything that needs broad coverage. What I'd change:
not tune the frozen rules against this gold set — that would be the exact violation this project is built
to avoid — but build a `rule-v2` with looser Macroeconomic keyword matching, scored on a *fresh* sample,
and compare the two versions' precision/recall tradeoff explicitly rather than just chasing a higher number.

**29. Why are Credit Event and Geopolitical classes "unvalidated" — only 1 and 2 examples?**
Because the 200-row gold sample was drawn from the real cached corpus (Mastodon live posts + historical
tweet replay), and those two event types are simply rare in that specific mix — this is a property of the
data available, not a sampling bug. With n=1 and n=2, no precision/recall number for those classes means
anything statistically — a single example could be right or wrong by pure chance. The honest move, which
this submission takes, is to say plainly that these classes can't be evaluated yet rather than report a
0% or 100% figure computed from 1-2 examples as if it were a real measurement. Fixing this needs more
Credit-Event/Geopolitical-rich source data (real financial news, which is exactly what GDELT would have
provided before it was rate-limited) or a much larger gold sample drawn from a source where those classes
are more common.

**30. I heard the gold-label set was contaminated at one point — what happened, in plain terms?**
The labelling tool had a shortcut: a single keystroke ('s') that accepted the classifier's own suggested
label directly as the "human" gold label, with no record of which rows used it. That's circular — scoring
a classifier against a gold set partly made of that same classifier's own guesses doesn't measure
anything. I didn't try to figure out afterward which specific rows had used the shortcut (there was no way
to know); instead the entire 200-row set was discarded and re-labelled from scratch, blind — the tool no
longer shows the classifier's suggestion at all, the shortcut is removed entirely (not just discouraged),
and every label now carries a `label_source=human_blind` stamp. The scoring script refuses to run unless
every single row has that stamp. The 88.5%/84.0%/34% numbers in this submission are from that clean,
re-labelled set.

**31. GDELT returned 0 articles and the impact-score event study never ran — so the Impact Score itself is
unvalidated. Why should I trust the trigger threshold of 7, specifically?**
Short answer: you shouldn't trust that "7" is the statistically optimal cutoff — no validation exists to
support that specific number over, say, 6 or 8. It's a round-number, documented-as-illustrative threshold
(`config/scenarios.yaml`), not a tuned one. What the threshold *does* do, mechanically, is combine with the
impact formula's own components (sentiment magnitude, event severity prior, source breadth, entity
importance, novelty) to require a genuinely unusual, high-conviction story before firing a stress test —
in practice, out of 76 real signals, exactly 3 clear both the impact>7 and sentiment<0 gates, which is a
plausible-looking selectivity, but "plausible-looking" is not the same as "empirically validated," and I
want that distinction to be explicit rather than implied.
