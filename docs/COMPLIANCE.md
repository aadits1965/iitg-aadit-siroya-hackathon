# Compliance Checklist — S&P Global & Crisil Campus Hackathon 2026

Ticked only when verified with evidence (file path / command output). Updated at the end of every phase.

## Problem brief
- [x] Core AI/NLP Risk Engine ingests text from >= 2 distinct sources (news + social). Evidence: Mastodon
      (live, 73 real posts cached) + Twitter-replay (300 real rows) both running through the same engine,
      89 signals produced. GDELT (news) adapter built and unit-tested but not yet live-verified end-to-end
      (sandbox network block — see docs/USER_TODO.md for the one-time cache-build step).
- [x] Outputs Sentiment Score (-1..1), Event Classification, Impact Score (1-10) per doc/entity. Evidence:
      `results/signals.jsonl`, 89 real signals, each with sentiment/event/impact blocks + component breakdown.
- [x] Signals available downstream via API and/or file. Evidence: `results/signals.jsonl` +
      `GET /signals` (FastAPI), both tested against real data.
- [x] At least one downstream module built (Module B — Strategic Portfolio Stress Testing). Evidence:
      `scripts/run_stress_test.py` ran end-to-end against real signals, real portfolio, real market data.
- [x] Module B: subscribes to Event Class + Impact Score (`trigger.py`, 3/76 real signals fired after the
      entity-linking/event-classification fixes); synthetic portfolio with loans+bonds+derivatives
      (50 positions, 5 asset classes); high-impact event triggers stress test (impact>7 threshold,
      cooldown). Evidence: `results/stress_test_output.json`.
- [x] Dashboard shows portfolio value before vs after. Evidence: `src/dashboard/app.py` Stress Test tab,
      verified end-to-end via `run.py --mode demo` (see PROGRESS.md Phase 5).

## Submission package
- [ ] Public GitHub repo named `iitg-aadit-siroya-hackathon`.
- [ ] Structure matches: README.md, requirements.txt, LICENSE (MIT), src/, data/, docs/presentation.pdf,
      docs/architecture.png.
- [ ] README follows mandatory template exactly, exact run command in Quickstart.
- [ ] Deck: 5-7 slides PDF at docs/presentation.pdf.
- [ ] Demo video: YouTube Unlisted, link in README, target <= 5:00 (see §2 of the build prompt re: conflicting
      10-min vs 5-min instructions — resolved to <=5:00).
- [ ] All data (incl. synthetic) in /data with sources+assumptions in README "Dataset Used".
- [ ] Clean clone runs using only README commands.
- [ ] Ready for live jury pitch + Q&A.

## Status
Phase 0 (setup & verification) in progress. See PROGRESS.md for phase-by-phase log.
