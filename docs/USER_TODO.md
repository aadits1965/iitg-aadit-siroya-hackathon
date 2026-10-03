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
```

Don't label the current committed `data/eval/event_gold.csv` (200 rows, but Mastodon/Twitter-only, zero
"Product Launch" examples) — regenerate it first so your labelling time goes toward a sample that actually
covers all six event classes.

## 4. Everything else

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
