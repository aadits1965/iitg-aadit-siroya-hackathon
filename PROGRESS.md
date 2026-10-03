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
