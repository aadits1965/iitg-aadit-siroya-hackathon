# Things Only Aadit Can Do

- [ ] **Run `python scripts/build_cache.py` once from a normal (non-shared, non-datacenter) network** — e.g.
      your laptop on home/college wifi — to populate `data/cache/news_gdelt.jsonl` with real GDELT headlines.
      The dev sandbox's shared IP is persistently rate-limited/blocked by GDELT and several news RSS feeds
      (confirmed HTTP 429/403 on every retry); this is an IP-reputation issue with the sandbox, not with
      GDELT itself. See `docs/DATA_VERIFICATION.md` §8 for the full evidence trail.
- [ ] **Confirm with organisers:** the guidelines doc says demo video = "10 mins screen recording" but the
      platform's Required Deliverables says live demo "not to exceed 5 minutes". This build targets **<=5:00**
      to satisfy both readings. Confirm which is authoritative if possible.
- [ ] **Confirm the judging rubric weights** beyond the stated tie-breakers (Domain Understanding, then
      Presentation & Communication, then earliest timestamp) — not provided in the brief.
- [ ] **Label the event-classification gold set.** `data/eval/event_gold.csv` currently has **110 real rows**
      (sampled from the 373 real cached Mastodon + replay-tweet docs, stratified by the rule baseline's own
      guess) — run `python scripts/label_events.py` to fill in `gold_label` by hand; it saves after every row
      so you can stop and resume. This is a human-judgement task, not something to fabricate.
      **After you run `scripts/build_cache.py` from a clean network** (GDELT item above), re-run
      `python scripts/sample_event_gold.py` first to regenerate the sample with GDELT headlines included —
      the current 110-row sample has zero "Product Launch" examples and is Mastodon/Twitter-only, so the
      full run will give better class coverage before you spend time labelling.
- [ ] **Run `python scripts/run_impact_event_study.py`** after the GDELT cache-build step above — this
      produces the real Impact Score validation result (Spearman correlation vs realised abnormal returns).
      Only 4 real ticker-linked, real-timestamped documents exist in this dev environment so far (not enough
      to report a correlation; see docs/EVALUATION.md section 3) — this script needs the larger GDELT sample
      to produce a meaningful number. If the result comes back weak/null, that's a real finding to report
      honestly in the deck, not a reason to re-run until something better appears.
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
