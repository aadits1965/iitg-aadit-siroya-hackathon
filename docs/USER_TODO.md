# Things Only Aadit Can Do

## Local steps, in order

Run these from a normal network (home/college wifi, not the dev sandbox this was built in — GDELT,
Treasury, and Yahoo Finance are all confirmed unreachable from there, see `docs/DATA_VERIFICATION.md`
sections 8-9).

### 1. Set up and build the cache

```bash
git clone <repo-url>
cd iitg-aadit-siroya-hackathon
python -m venv .venv
.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt

# Optional: put a free FRED API key in .env (copy .env.example -> .env first) so
# credit-spread series get fetched too. Skip if you don't want to sign up -- Module B
# still runs on documented illustrative spread assumptions without it.

python scripts/build_cache.py
```

**Expected runtime: ~15-20 minutes**, dominated by GDELT's own 5-second self-throttle across ~100 queries
(16 core-universe + ~80 widened event-study-universe) and ~80 individual yfinance price downloads. Faster
partial run: `python scripts/build_cache.py --skip-event-study` (~5 min, but the event study in step 4
will stay underpowered) or `--skip-market-data`.

This also replaces the PROVISIONAL Treasury curve / equity prices (Claude fetched these manually via
WebFetch on 2026-10-04 because this dev sandbox can't reach treasury.gov/Yahoo Finance directly) with a
freshly, directly-fetched, non-provisional snapshot — expected and fine.

### 2. Regenerate the event-classification gold sample

```bash
python scripts/sample_event_gold.py
```

Re-run now that real GDELT data exists — the currently-committed `data/eval/event_gold.csv` (200 rows) is
Mastodon/Twitter-only with zero "Product Launch" examples; this regenerates it with much better class
coverage across all six classes before you spend labelling time on it.

### 3. Label the gold set and score the frozen classifier

```bash
python scripts/label_events.py            # interactive, saves after every row, safe to stop and resume
python scripts/score_event_classifier.py  # scores the FROZEN rule-v1 (git tag classifier-v1) once
```

**Do not edit `RULE_KEYWORDS`/`CREDIT_MARKET_INDICATORS` in `src/nlp/event_classification.py` based on
what this reports and re-run it** — that would be tuning on the eval set. If the frozen classifier scores
poorly, that's a real, reportable finding (it's already on the deck's Limitations slide as "pending" and
will show the real number once this step is done) — a genuine improvement is a new `rule-v2`, scored on a
different/fresh sample, not this one.

### 4. Run the impact-score event study, then verify the market data

```bash
python scripts/run_impact_event_study.py
python scripts/verify_provisional_data.py
```

The event study produces the real Impact Score validation result (Spearman correlation vs realised
abnormal returns, with its 95% CI — see `docs/EVALUATION.md` section 3 for why n>=200 matters). **If the
result comes back weak, null, or still underpowered, that's a real finding — the README/deck generators
already state "no statistically significant relationship" or "UNDERPOWERED" automatically in that case;
don't re-run hoping for a better number.** `verify_provisional_data.py` should report MATCH now that
step 1 replaced the provisional snapshot — if it reports a mismatch instead, investigate before trusting
the stress-test numbers.

### 5. Regenerate the real pipeline output, then metrics/README/deck

```bash
python run.py --mode demo --recompute --no-dashboard   # rebuilds signals.jsonl + stress_test_output.json; Ctrl+C once it says the API is up
python scripts/generate_readme.py
python scripts/generate_architecture_diagram.py
python scripts/generate_deck_charts.py
python scripts/generate_deck.py
```

Each generator **refuses to run** (raises, exits non-zero) if a number it needs is missing — if any of
these fail, it means an earlier step in this list didn't complete. The README and deck's Key Results /
Limitations sections automatically pick up the real event-classification and impact-study numbers from
step 3-4 once they exist — no manual editing needed.

### 6. Export the deck to PDF, capture dashboard screenshots, finish the repo

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
and the deck's fallback text, so this is safe to show as long as you say the same thing out loud. **Re-check
after step 1 above** — the real GDELT pull may surface a genuine high-impact Geopolitical headline the
current Mastodon/Twitter-only cache doesn't have.

## Phase 11: re-run the clean-clone + fresh-venv check

A clean-clone + fresh-venv install was run once during the build (in the dev sandbox, which has shown
wildly inconsistent install times throughout — anywhere from ~5 to ~22 minutes for the same `pip install`)
and passed (120/120 tests, 1 opt-in skipped). **Re-run it again after you've done steps 1-6 above**, since
the final committed state (with your real gold labels, event-study result, and PDF) hasn't been through a
clean-clone check yet:

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
