# Demo Video Script (target: ≤5:00)

Use **demo mode**, not live mode, so the walkthrough is deterministic and repeatable:
`python run.py --mode demo` (loads the committed `results/` as-is — no FinBERT recompute, no network —
confirmed to start in well under 30 seconds; see `docs/USER_TODO.md` if you want to show the
`--recompute` rebuild instead, but that adds ~60-90s and isn't necessary for this script).

Every number below is real, pulled from the actual committed `results/signals.jsonl` and
`results/stress_test_output.json` as of this script being written — if you regenerate the pipeline
output (`docs/USER_TODO.md` step 5) before recording, **re-check these numbers against the dashboard
on screen** and adjust the spoken lines to match what's actually showing, rather than reading this
script's numbers over different numbers on screen.

---

## 0:00 – 0:30 — Intro (30s)

**[Title card / talking head]**

> "Risk and ratings teams can't manually read every headline fast enough to know what it means for a
> portfolio. This is an AI/NLP Risk Engine that turns news and social text into structured risk signals —
> sentiment, event type, a transparent Impact Score — and feeds them straight into a real portfolio stress
> test. I'm Aadit Siroya, this is my submission for the S&P Global & Crisil Campus Hackathon."

## 0:30 – 1:00 — Setup / Run (30s)

**[Terminal, from a clean checkout]**

> "Setup is one command after `pip install`."

Type and run:
```bash
python run.py --mode demo
```

> "No recompute, no network call — it loads the signals and stress-test output that are already in the
> repo, so this starts in a few seconds."

**[Browser opens to the dashboard, Live Signal Feed tab visible]**

## 1:00 – 3:30 — End-to-end walkthrough (2.5 min)

### 1:00 – 1:35 — Live Signal Feed tab

> "This is the signal feed — every document that came in through the ingestion pipeline, scored for
> sentiment with FinBERT, classified into one of six event types, and given an Impact Score from 1 to 10."

**[Sort/filter to a high-impact signal, click it to show the component breakdown chart]**

> "Each score is explainable — you can see exactly which components drove it: sentiment magnitude, the
> event class's severity prior, how many sources covered the story, entity importance, and novelty."

### 1:35 – 2:05 — Engine Quality tab

**[Switch to Engine Quality tab]**

> "Before trusting any of this, I evaluated it. FinBERT scores 0.660 macro-F1 against a held-out set it
> was never trained on, versus 0.453 for a naive lexicon baseline and 0.267 for just guessing the majority
> class — and those confidence intervals don't overlap, so that's a real improvement, not noise."

**[Point at the bearish-recall number]**

> "For a risk engine, catching real bearish signals matters most — FinBERT's bearish recall is 76.5%,
> versus 53% for the naive baseline."

### 2:05 – 3:10 — Stress Test tab

**[Switch to Stress Test tab]**

> "This is Module B — the engine's signals trigger a real stress test against a synthetic 50-position
> wholesale portfolio: loans, bonds, swaps, options, FX forwards."

**[Point at the headline scenario]**

> "This result came from a real triggered signal, not a manual pick — a headline about U.S. inflation
> data, classified Macroeconomic, which fired the Fed's own severely-adverse scenario: equities down 54%,
> long rates down 200 basis points, credit spreads blown out. Portfolio value moves from $657 million to
> $644 million."

**[Point at the MTM / credit-loss split]**

> "I keep mark-to-market P&L and credit loss on loans as two separate numbers, deliberately — a loan is
> never both fair-valued *and* provisioned for the same credit deterioration, which would double-count it."

**[Point at the naive-vs-full-reprice chart]**

> "And I didn't just reprice once — I compared the full cashflow reprice against the naive duration-only
> approximation the brief asked for. The gap grows with shock size — that's real convexity, not a
> coincidence."

### 3:10 – 3:30 — Scenario Explorer (brief)

**[Switch to Scenario Explorer, pick a different event class, click Run]**

> "For live questions, I can run any scenario manually too — this one's clearly labelled 'manual
> scenario, not triggered by a real signal,' so it's never confused with the real result you just saw."

## 3:30 – 4:15 — Results & impact (45s)

**[Back to a summary view, or talking head]**

> "End to end: raw text in, a dollar P&L number out, fully traceable — signal, scenario, shock, P&L — and
> every number on this dashboard is read from a file a script actually produced, nothing typed in by
> hand. That traceability, and being upfront about what's still pending — like the event-classification
> score, which needs hand-labelled data I'm finishing separately — is what I think actually matters for a
> risk and ratings use case: not a flashier demo, but one you can audit."

**[End card: repo link, candidate name]**

---

## Timing budget check

| Segment | Duration | Cumulative |
|---|---|---|
| Intro | 0:30 | 0:30 |
| Setup/Run | 0:30 | 1:00 |
| Live Signal Feed | 0:35 | 1:35 |
| Engine Quality | 0:30 | 2:05 |
| Stress Test | 1:05 | 3:10 |
| Scenario Explorer | 0:20 | 3:30 |
| Results & impact | 0:45 | 4:15 |
| **Buffer** | **0:45** | **5:00** |

Leaves ~45 seconds of slack for pacing — use it, don't rush the Stress Test section, it's the part that
actually demonstrates Module B.

## Before recording

- [ ] Confirm `results/signals.jsonl` and `results/stress_test_output.json` reflect what you want to show
      (re-run `docs/USER_TODO.md` steps 1-5 first if you want the real GDELT-triggered signals/event-study
      result instead of the current Mastodon/Twitter-only state).
- [ ] Confirm the headline scenario is still real (not "no real signal has fired" — check `n_fired` in
      `results/stress_test_output.json` is > 0) — if it's gone to zero, adjust the Stress Test section's
      spoken lines or re-run the pipeline.
- [ ] Time a full dry run before recording for real — target ≤5:00, this script budgets to 4:15 with
      45s slack, but actual delivery pace will vary.
