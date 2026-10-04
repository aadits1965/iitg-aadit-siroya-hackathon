# Q&A Prep — Red-Teaming This Project as a Hostile S&P/Crisil Judge

Honest answers, not deflections. Where the honest answer is "this is a real limitation," it says so —
that's the point of this document.

## Core methodology

**1. Why should I believe the Impact Score means anything?**
Right now, you shouldn't fully — the event-study validation (Spearman correlation between Impact Score
and realised abnormal returns) is pending a real GDELT sample (n≥200 for adequate power; see
`docs/EVALUATION.md` section 3). The methodology is implemented and mechanically verified (hand-built
price series, no-look-ahead date alignment), but GDELT is unreachable from the dev environment this was
built in. Until that result exists, the Impact Score should be read as a **transparent, documented
rule-based severity score** — every component is visible — not an empirically-validated predictor.

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
volume without batching/GPU. GDELT's real rate limits weren't even reachable to test properly from this
dev environment (persistent 429s — see below). No adversarial-text defences are implemented; a
coordinated fake-headline campaign would be scored at face value.

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

**14. What's "provisional" market data, and why?**
The Treasury yield curve and 5 equity spot prices in this submission were fetched via a tool (WebFetch)
that passes page content through a summarising model, because this dev sandbox's direct network calls to
treasury.gov and Yahoo Finance fail outright (confirmed, not assumed). It's real, live-fetched data, not
fabricated — but not independently verified byte-for-byte either. `scripts/verify_provisional_data.py`
cross-checks it against a direct download once run from a normal network. The Fed stress-scenario numbers
are *not* provisional — those were re-sourced via a direct `curl` to federalreserve.gov (reachable
directly, unlike Treasury/Yahoo) and parsed from the raw HTML table.

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
The current cache is Mastodon-live-posts and a replayed historical-tweet dataset — genuinely Geopolitical,
high-impact stories are rare in that mix. The wider real GDELT pull (pending a normal network connection)
is expected to surface more variety.

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
Run the real GDELT pull and finish the two pending evaluations (event classification, impact-score study)
— both are fully built and waiting on that one data source.
