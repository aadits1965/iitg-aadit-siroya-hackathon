# Compliance Checklist — S&P Global & Crisil Campus Hackathon 2026

Ticked only when verified with evidence (file path / command output). Updated at the end of every phase.

## Problem brief
- [ ] Core AI/NLP Risk Engine ingests text from >= 2 distinct sources (news + social).
- [ ] Outputs Sentiment Score (-1..1), Event Classification, Impact Score (1-10) per doc/entity.
- [ ] Signals available downstream via API and/or file.
- [ ] At least one downstream module built (Module B — Strategic Portfolio Stress Testing).
- [ ] Module B: subscribes to Event Class + Impact Score; synthetic portfolio with loans+bonds+derivatives;
      high-impact event triggers stress test; dashboard shows value before vs after.

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
