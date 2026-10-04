# AI/NLP Risk Engine & Strategic Portfolio Stress Test - S&P Global & Crisil Campus Hackathon

**Candidate Name:** Aadit Siroya
**College Email ID:** s.aadit@iitg.ac.in
**College / Campus:** IIT Guwahati
**Demo Video Link:** [YouTube Unlisted - to be added before submission, see docs/USER_TODO.md]
**Slide Deck Link (if hosted externally):** [docs/presentation.pptx in this repo]

## 1. Project Overview / Problem Statement & Approach

Risk and ratings teams are drowning in unstructured text - thousands of news headlines and social posts a
day, most of it noise. The question this project answers is: can a lightweight NLP pipeline turn that
firehose into structured, actionable risk signals fast enough and honestly enough to be useful, and can
those signals drive a real portfolio stress test rather than just a sentiment dashboard?

The AI/NLP Risk Engine ingests text from two distinct source types (news and social media), scores each
document for sentiment (-1 to 1), classifies it into one of six event categories, and computes a
transparent, component-by-component Impact Score (1-10). Signals are published both to a flat file and a
FastAPI endpoint, so downstream consumers can poll either. **Module B (Strategic Portfolio Stress Testing)**
subscribes to these signals: when a signal's Impact Score crosses a threshold, it fires a scenario-specific
shock against a synthetic 50-position wholesale banking portfolio (loans, bonds, interest-rate swaps,
equity options, FX forwards) and reports the resulting mark-to-market P&L and credit loss separately.

The build approach throughout was to verify every external claim live rather than assume it, and to refuse
to report a number that wasn't actually produced by a script. Several premises in the original brief turned
out to be false on inspection - X/Twitter has no free read API in 2026, FinBERT is fine-tuned on the exact
dataset the brief's own evaluation plan would have used, "price target" collides with a naive "Target Corp"
name match - and the build adapted around each one rather than working around it silently. The full
verification trail is in `docs/DATA_VERIFICATION.md`.

## 2. Architecture & Tech Stack

![Architecture](architecture.png)

**Data flow:** News (GDELT) and social (Mastodon live + a licensed historical-tweet replay fallback) ->
ingestion adapters with de-duplication -> NLP Risk Engine (entity linking, FinBERT sentiment, rule-based
event classification, composite Impact Score) -> signal store (JSONL + SQLite) + FastAPI `/signals` endpoint
-> Module B trigger engine -> full-reprice portfolio revaluation -> Streamlit dashboard.

**Frameworks & libraries:** FastAPI + uvicorn (signal API), Streamlit + Plotly (dashboard), Hugging Face
Transformers (`ProsusAI/finbert`), VADER (naive sentiment baseline), pydantic (schemas), SQLite (signal
store), scipy/scikit-learn (evaluation statistics), pandas/numpy (data handling), python-pptx (deck
generation).

## 3. Dataset Used

| Source | Nature | Licence | Size (cached) | Notes |
|---|---|---|---|---|
| GDELT DOC 2.0 | Public news headlines | CC0 | varies (live/cached) | Headline-level only - the API has no article-body field (confirmed live) |
| Mastodon public hashtag timelines | Live social posts | Public API, no auth | 73 real posts cached | Confirmed working live; see `docs/DATA_VERIFICATION.md` section 8 |
| `zeroshot/twitter-financial-news-sentiment` (Hugging Face) | Historical tweet replay (offline fallback) | MIT | 300 rows cached | No real timestamps - synthetic, flagged in every row; excluded from the event study |
| US Treasury daily par yield curve | Market data | Public domain | 1 dated snapshot | **PROVISIONAL** - see section 5 and `docs/DATA_VERIFICATION.md` section 9 |
| Yahoo Finance (via a verified-working fetch path) | Equity spot prices | Public | 5 tickers, 1 date | **PROVISIONAL**, same caveat |
| Federal Reserve severely-adverse stress scenario | Macro shock magnitudes | Public | 1 scenario table | SOURCED directly (not provisional) - see `docs/DATA_VERIFICATION.md` section 10 |

All data and assumptions (rating-to-PD mapping, shock library magnitudes, the EL horizon choice, the
sector-contagion assumption for mapping real-company signals onto fictional counterparties, and more) are
documented with their justification in `docs/ASSUMPTIONS.md` - nothing here is an unstated guess.

## 4. Quickstart & Installation

Runtime: Python 3.11, CPU-only, tested on Windows 11.

```bash
git clone <repo-url>
cd iitg-aadit-siroya-hackathon
python -m venv .venv
.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python run.py --mode demo
```

`--mode demo` is fully offline and deterministic (verified: two clean runs produce byte-identical
`results/signals.jsonl`, see `tests/test_demo_idempotency.py`). First run downloads FinBERT's weights
(~440MB, ~83s one-time; confirmed live timing in `docs/EVALUATION.md`). `--mode live` pulls fresh data
first via `scripts/build_cache.py` - see `docs/USER_TODO.md` for why that needs a normal network connection
rather than this project's dev sandbox.

## 5. Key Results & Domain Impact

{{KEY_RESULTS_SECTION}}

## Limitations & Next Steps

- **Impact Score validation is incomplete in this environment.** GDELT is unreachable from the dev sandbox
  this was built in (confirmed, `docs/DATA_VERIFICATION.md` section 8); the event-study correlation needs
  the resulting larger sample (n>=200 for adequate statistical power) to be meaningful. Infrastructure is
  built and mechanically verified; see `docs/EVALUATION.md` section 3 and `docs/USER_TODO.md`.
- **Event classification accuracy is pending human labelling** of `data/eval/event_gold.csv`. The rule
  classifier is frozen at `rule-v1` (git tag `classifier-v1`) specifically so this score, once produced,
  reflects an honest, un-tuned evaluation.
- **English-only.** Non-English documents are filtered at ingestion.
- **Headline-level NLP for GDELT**, not full article text - the API has no body field, and this project
  does not scrape article bodies.
- **The social-source replay is historical, not live** - timestamps are synthetic, and the content predates
  this project's 2026 setting, creating a real temporal mismatch against the portfolio's 2026-10-02 market
  snapshot. Documented plainly, never presented as a real-time read (`docs/ASSUMPTIONS.md`).
- **Market data (Treasury curve, equity spot) is PROVISIONAL** in this submission - fetched via a tool that
  passes content through a summarising model rather than a direct download, because this dev sandbox cannot
  reach treasury.gov/Yahoo Finance directly. `scripts/verify_provisional_data.py` exists to cross-check it;
  see `docs/USER_TODO.md`.
- **Sector/country contagion, not name-matching**, maps a real-company signal onto the fictional portfolio
  (no fictional position IS the named real company) - an explicit, documented assumption.
- **The Fed scenario's peak/trough is applied as one instantaneous shock**, not its real ~2-year quarterly
  path.
- **Credit loss is a 1-year EL (Basel-style), not IFRS 9 lifetime ECL** - a real stress scenario would
  typically trigger Stage 2/3 staging, so this project's stressed credit-loss figures are a lower bound.
- **Next steps:** finish the three pending evaluations above once real GDELT/market data is available;
  consider Module A (tactical rebalancing) if time permits; replace the provisional market-data snapshot
  with a directly-fetched one.

## AI Assistance Disclosure

AI coding assistance (Claude) was used throughout this build for implementation, debugging, and
documentation. All design decisions, scope calls, dataset/assumption choices, and the event-classification
gold-label judgements are the candidate's own. Every external claim in this repo (API capabilities, licence
terms, dataset properties, model behaviour) was independently verified against a live source rather than
assumed - the verification trail is in `docs/DATA_VERIFICATION.md`. Disclosed per rule 6 ("AI usage is
generally allowed... provided it is used with integrity and full academic/professional honesty").
