# Things Only Aadit Can Do

## 1. One-time local data build (do this first, from a normal network — home/college wifi, not the dev
sandbox this was built in; GDELT, Treasury, and Yahoo Finance are all confirmed unreachable from there —
see `docs/DATA_VERIFICATION.md` sections 8-9)

```bash
# from the repo root
python -m venv .venv
.venv\Scripts\activate          # Windows; use `source .venv/bin/activate` on macOS/Linux
pip install -r requirements.txt

# Optional but recommended: put a free FRED API key in .env (copy .env.example -> .env first)
# so credit-spread series get fetched too. Skip if you don't want to sign up -- Module B still
# runs on documented illustrative spread assumptions without it.

python scripts/build_cache.py
```

**Expected runtime: ~15-20 minutes**, dominated by GDELT's own 5-second self-throttle across ~100 queries
(16 core-universe + ~80 widened event-study-universe) and ~80 individual yfinance price downloads. If you
want a faster partial run first: `python scripts/build_cache.py --skip-event-study` (skips the ~80-query
widened pull, ~5 min instead) or `--skip-market-data`.

**Output files it writes:**
- `data/cache/news_gdelt.jsonl` — core 20-ticker news (used by the dashboard / Module B signal feed)
- `data/cache/news_gdelt_event_study.jsonl` — wide 80-ticker news (used only to get the event study's
  sample size up — see `docs/EVALUATION.md` section 3)
- `data/cache/social_mastodon.jsonl` — refreshed live social posts
- `data/cache/market/treasury_par_yield_curve.csv` — replaces the one Claude fetched manually via WebFetch
  on 2026-10-04 (see that file's header comment) with a freshly, directly-fetched snapshot — expected and fine
- `data/cache/market/equity_prices.csv` — ~550 days of daily closes for all universe + event-study tickers
- `data/cache/market/fred_series.csv` — only if `FRED_API_KEY` is set in `.env`

## 2. Then run the impact-score event study

```bash
python scripts/run_impact_event_study.py
```

Produces the real Impact Score validation result (Spearman correlation vs realised abnormal returns,
with its 95% CI and a mean-|AR|-by-decile table — see `docs/EVALUATION.md` section 3 for why this needs
n>=200 to be meaningful). Runtime: a few minutes (FinBERT over however many docs got linked to a ticker).
**If the result comes back weak, null, or still underpowered, that's a real finding — report it honestly
in the deck as-is, don't re-run hoping for a better number.**

## 3. Then regenerate and label the event-classification gold set

```bash
python scripts/sample_event_gold.py      # re-run now that GDELT data exists -- much better class coverage
python scripts/label_events.py           # interactive, saves after every row, safe to stop and resume
python scripts/score_event_classifier.py # scores the FROZEN rule-v1 classifier (git tag classifier-v1) once
```

Don't label the current committed `data/eval/event_gold.csv` (200 rows, but Mastodon/Twitter-only, zero
"Product Launch" examples) — regenerate it first so your labelling time goes toward a sample that actually
covers all six event classes. **`score_event_classifier.py` scores the classifier exactly as it is tagged
`classifier-v1` right now** — do not edit `RULE_KEYWORDS`/`CREDIT_MARKET_INDICATORS` based on what it
reports and re-run it; that would be tuning on the eval set. If the frozen rules turn out to score poorly,
that's a real, reportable finding (put it on the Limitations slide) — a genuine improvement is a new
`rule-v2`, scored on a different/fresh sample, not this one.

## 4. Demo story: no real Geopolitical trigger exists yet in the cached data

**Checked directly** (`results/signals.jsonl`, current cache): exactly **1** Geopolitical-classified signal
exists in the whole 76-signal cached corpus, at impact **6.35** — below the 7.0 trigger threshold. **There
is currently no real, non-manual signal that is both Geopolitical and impact > 7**, so Module B's
`geopolitical_rate_shock` tier (the brief's own "equities -10%, rates +200bp" example) has never actually
fired from real data in this environment. If the demo/pitch wants to show that specific scenario, use the
dashboard's **Scenario Explorer** tab (manually pick "Geopolitical") — it is already labelled in the UI as
computing live rather than reading a real trigger, and the deck must say the same if it shows this scenario
(**"manual scenario" labelled visibly, never presented as a real triggered signal**). **Re-check this after
your local GDELT cache-build run** (step 1 above) — the wider, real GDELT news pull may well surface a
genuine high-impact Geopolitical headline that the current Mastodon/Twitter-only cache doesn't have.

## 5. Everything else

- [ ] **Confirm with organisers:** the guidelines doc says demo video = "10 mins screen recording" but the
      platform's Required Deliverables says live demo "not to exceed 5 minutes". This build targets **<=5:00**
      to satisfy both readings. Confirm which is authoritative if possible.
- [ ] **Confirm the judging rubric weights** beyond the stated tie-breakers (Domain Understanding, then
      Presentation & Communication, then earliest timestamp) — not provided in the brief.
- [ ] **Record the demo video** per `docs/DEMO_SCRIPT.md` (Phase 10), upload to YouTube as **Unlisted**, and
      test the link in an incognito window before submitting.
- [ ] **Make the GitHub repo public** before submission and open it logged-out to confirm it's visible.
- [ ] **Verify the slide deck link** (if hosted outside the repo) opens for "Anyone with the link", tested
      in an incognito window.
- [ ] **Submit** repo link + video link + deck link via the official submission form before the deadline
      (**2026-10-11**, per your "7 days from today" answer — reconfirm the exact time with organisers).
- [ ] **Keep the demo runnable** on your machine for the live jury pitch slot.
- [ ] Deadline and college email used throughout this build: **2026-10-11**, **s.aadit@iitg.ac.in** — flag me
      immediately if either is wrong so I can fix every reference.
