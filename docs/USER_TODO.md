# Things Only Aadit Can Do

## GDELT is abandoned for this submission (as of 2026-10-18)

GDELT returned HTTP 429 (rate-limited) on every query for 2+ hours on a real local run. Per instruction,
it is **not retried** for this submission. Two consequences, both already reflected everywhere (README,
deck, `results/metrics.json`, `docs/ASSUMPTIONS.md` "Impact-score event study: not run"):

- The **impact-score event study was never run** — `results/metrics.json`'s `impact_score_event_study` key
  records `"status": "not_run"` with the exact reason, not a number. There is no further local step for
  this unless a different news source is substituted (not currently planned).
- The **event-classification gold-set resampling step that used to be here is gone** — it depended on a
  real GDELT pull that isn't happening. The currently-committed `data/eval/event_gold.csv` (200 rows,
  Mastodon/Twitter-only, zero "Product Launch" examples — a real, stated limitation, not hidden) is what
  you have to label. `python scripts/label_events.py` (interactive, resumable), then
  `python scripts/score_event_classifier.py` (scores the frozen `rule-v1`, git tag `classifier-v1`, once).
  **Do not edit `RULE_KEYWORDS`/`CREDIT_MARKET_INDICATORS` based on what this reports and re-run it** —
  that would be tuning on the eval set; a genuine improvement is a new `rule-v2` scored on a fresh sample.

## Local steps, in order

### 1. Set up and refresh market data

```bash
git clone <repo-url>
cd iitg-aadit-siroya-hackathon
python -m venv .venv
.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt

# Optional: put a free FRED API key in .env (copy .env.example -> .env first) so
# credit-spread series get fetched too. Skip if you don't want to sign up -- Module B
# still runs on documented illustrative spread assumptions without it.
```

Then run **`scripts/refresh_local.ps1`** (PowerShell) — this does everything below in one command:
market-only fetch (Treasury curve direct + FRED + JPM/NVDA equity spot — **no** GDELT/Mastodon/Twitter) ->
re-run the Module B stress test -> regenerate README + deck -> run the full test suite -> `git add` /
`git commit` / `git push`. Each step stops the script on failure, so nothing half-finished gets pushed.

```powershell
.\scripts\refresh_local.ps1
# or, to review before pushing yourself:
.\scripts\refresh_local.ps1 -SkipPush
```

Equivalent to running by hand:
```bash
python scripts/build_cache.py --market-only   # Treasury curve direct (never provisional) + FRED + JPM/NVDA spot
python scripts/run_stress_test.py
python scripts/generate_readme.py
python scripts/generate_deck_charts.py
python scripts/generate_deck.py
pytest tests/ -q
```

The old `python scripts/build_cache.py` (full run, news + social + market, ~15-20 min) still works if you
ever want Mastodon/Twitter-replay data refreshed too — just know it will still try GDELT and get
rate-limited (harmless, that step is wrapped in try/except and logs a warning, the rest of the run
continues).

### 2. Export the deck to PDF, capture dashboard screenshots, finish the repo

- **Export `docs/presentation.pptx` to `docs/presentation.pdf`** (open it in PowerPoint/LibreOffice/Google
  Slides and export/print to PDF) and commit it. LibreOffice isn't installed in the dev sandbox this was
  built in, so this step couldn't be automated — **the repo structure requires `docs/presentation.pdf`
  explicitly, and `scripts/audit_compliance.py` will fail until it's there.**
- **Capture these dashboard screenshots** (run `python run.py --mode demo` — now fast, no recompute by
  default — and screenshot each tab), saving to the exact paths below. The deck generator automatically
  uses a real screenshot in place of its generated chart on slide 5 for any of these that exist, re-run
  `python scripts/generate_deck.py` (and re-export the PDF) after adding them:
  - `docs/screens/live_signal_feed.png` — the Live Signal Feed tab, ideally with a high-impact signal selected
    so the component-breakdown chart is visible
  - `docs/screens/stress_test.png` — the Stress Test tab showing the real headline scenario (or, if a
    scenario is manually chosen, make sure the "🔶 Manual scenario — not triggered by a real signal" label
    is visible in the screenshot)
  - `docs/screens/scenario_explorer.png` — the Scenario Explorer tab after clicking "Run scenario" once,
    showing the "🔶 Manual scenario" label and a P&L result
- **Run `python scripts/audit_compliance.py`** — should print `AUDIT PASSED` once the PDF above is
  committed. Re-run the clean-clone + fresh-venv check too (Phase 11) — see the note below.

## Demo story: no real Geopolitical trigger exists yet in the cached data

**Checked directly** (`results/signals.jsonl`): exactly **1** Geopolitical-classified signal exists in the
76-signal cached corpus, at impact **6.35** — below the 7.0 trigger threshold. There is currently no real,
non-manual signal that is both Geopolitical and impact > 7. If the demo/pitch wants to show that specific
scenario, use the dashboard's **Scenario Explorer** tab (manually pick "Geopolitical") — every manual
result is now visibly labelled "🔶 Manual scenario — not triggered by a real signal" in both the dashboard
and the deck's fallback text, so this is safe to show as long as you say the same thing out loud. With
GDELT abandoned for this submission, this cached corpus (Mastodon + Twitter-replay only) is what the demo
has to work with — there is no further step expected to surface a real Geopolitical trigger.

## Phase 11: re-run the clean-clone + fresh-venv check

A clean-clone + fresh-venv install was run once during the build (in the dev sandbox, which has shown
wildly inconsistent install times throughout — anywhere from ~5 to ~22 minutes for the same `pip install`)
and passed (120/120 tests, 1 opt-in skipped). **Re-run it again after you've done steps 1-2 above**, since
the final committed state (with your real gold labels and the PDF) hasn't been through a clean-clone check
yet:

```bash
git clone <repo-url> /tmp/clean-check && cd /tmp/clean-check
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
pytest tests/ -q
python run.py --mode demo   # should start in a few seconds, no recompute
python scripts/audit_compliance.py
```

## Everything else

- [ ] **Confirm with organisers:** the guidelines doc says demo video = "10 mins screen recording" but the
      platform's Required Deliverables says live demo "not to exceed 5 minutes". This build targets **<=5:00**
      to satisfy both readings. Confirm which is authoritative if possible.
- [ ] **Confirm the judging rubric weights** beyond the stated tie-breakers (Domain Understanding, then
      Presentation & Communication, then earliest timestamp) — not provided in the brief.
- [ ] **Record the demo video** per `docs/DEMO_SCRIPT.md`, upload to YouTube as **Unlisted**, and test the
      link in an incognito window before submitting.
- [ ] **Make the GitHub repo public** before submission and open it logged-out to confirm it's visible.
- [ ] **Verify the slide deck link** (if hosted outside the repo) opens for "Anyone with the link", tested
      in an incognito window.
- [ ] **Submit** repo link + video link + deck link via the official submission form before the deadline
      (**2026-10-11**, per your "7 days from today" answer — reconfirm the exact time with organisers).
- [ ] **Keep the demo runnable** on your machine for the live jury pitch slot.
- [ ] Deadline and college email used throughout this build: **2026-10-11**, **s.aadit@iitg.ac.in** — flag me
      immediately if either is wrong so I can fix every reference.
