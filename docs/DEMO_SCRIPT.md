# Demo Video Script (target: ≤5:00)

Use **demo mode**, not live mode, so the walkthrough is deterministic and repeatable:
`python run.py --mode demo` (loads the committed `results/` as-is — no FinBERT recompute, no network —
starts in well under 30 seconds).

Every number below is real, pulled directly from the actual committed `results/signals.jsonl`,
`results/metrics.json`, and `results/stress_test_output.json` as of this script being written — if you
regenerate the pipeline output before recording, **re-check these numbers against the dashboard on screen**
and adjust the spoken lines to match what's actually showing, rather than reading this script's numbers
over different numbers on screen.

---

## 0:00 – 0:30 — Intro (30s)

**[Title card / talking head]**

> "Risk and ratings teams can't manually read every headline fast enough to know what it means for a
> portfolio. This is an AI/NLP Risk Engine that turns news and social text into structured risk signals —
> sentiment, event type, a transparent Impact Score — and feeds them into a real portfolio stress test.
> I'm Aadit Siroya, this is my submission for the S&P Global & Crisil Campus Hackathon."

## 0:30 – 1:00 — Setup / Run (30s)

**[Terminal, from the README's own commands — a clean checkout]**

> "Setup is exactly the commands in the README."

Type and run (as written in the README's Quickstart):
```bash
pip install -r requirements.txt
python run.py --mode demo
```

> "No recompute, no network call — it loads the signals and stress-test output already in the repo, so
> this starts in a few seconds."

**[Browser opens to the dashboard, Live Signal Feed tab visible]**

## 1:00 – 1:30 — Live Signal Feed (30s)

> "This is the signal feed — 76 real documents, each scored for sentiment with FinBERT, classified into one
> of six event types, and given an Impact Score from 1 to 10."

**[Sort to the highest-impact signal, click it to show the component breakdown chart]**

> "Each score is explainable — sentiment magnitude, the event class's severity prior, source breadth,
> entity importance, and novelty."

## 1:30 – 2:00 — Audit Log (30s)

**[Switch to Audit Log tab]**

> "Every signal gets evaluated against the trigger rule — impact above 7 **and** sentiment below zero,
> with a cooldown so one story doesn't fire repeatedly. That sentiment gate is deliberate: I found two
> strongly *positive* headlines — an analyst upgrade, a positive rating note — that had fired the stress
> test on impact alone before I added it, because Impact Score measures how much a story matters, not
> whether it's good or bad news. Out of 76 signals evaluated, exactly 3 pass both conditions and fire."

**[Point at the 3 fired rows]**

## 2:00 – 2:50 — Stress Test (50s)

**[Switch to Stress Test tab]**

> "This is Module B — a real triggered signal, not a manual pick, fires a stress test against a synthetic
> 50-position wholesale portfolio: loans, bonds, swaps, options, FX forwards."

**[Point at the headline scenario]**

> "The highest-impact of the 3 fired signals — a headline about U.S. inflation data — triggered the Fed's
> own severely-adverse scenario on this synthetic portfolio. Portfolio value moves from $658.5 million to
> $644.7 million — a stressed loss of $13.79 million, or 2.09%."

**[Point at the MTM / credit-loss split]**

> "I keep mark-to-market P&L and credit loss as two separate numbers, deliberately — here that's +$1.3
> million of MTM gains against $15.1 million of credit loss on the loan book. A position is never both
> fair-valued *and* provisioned for the same deterioration, which would double-count it."

**[Point at the naive-vs-full-reprice chart]**

> "And I didn't just reprice once — I compared the full cashflow reprice against the naive duration-only
> approximation the brief asked for. The error is small at typical shocks but grows with shock size — real
> convexity, not a coincidence."

## 2:50 – 3:15 — Scenario Explorer (25s)

**[Switch to Scenario Explorer, pick a different event class, click Run]**

> "For live questions, I can run any scenario manually too — this one's clearly labelled 'manual scenario,
> not triggered by a real signal,' so it's never confused with the real result you just saw."

## 3:15 – 3:45 — Engine Quality (30s)

**[Switch to Engine Quality tab]**

> "Before trusting any of this, I evaluated it. FinBERT scores 0.660 macro-F1 against a held-out set, versus
> 0.453 for a naive lexicon baseline and 0.267 for just guessing the majority class. Event classification —
> scored against 200 blind hand-labelled examples, with no shortcut — is 88.5% accurate versus an 84.0%
> always-'Other' baseline. The gap that matters: it only catches 34% of true Macroeconomic headlines, even
> though it's never wrong when it does call one."

## 3:45 – 4:30 — Results & limitations (45s)

**[Back to a summary view, or talking head]**

> "End to end: raw text in, a dollar P&L number out, fully traceable — signal, scenario, shock, P&L — and
> every number on this dashboard is read from a file a script actually produced, nothing typed in by hand.
> I'm equally upfront about what's still weak: the event classifier misses most Macroeconomic headlines,
> Credit Event and Geopolitical classes have too few labelled examples to evaluate at all yet, and the
> Impact Score's own event-study validation never ran — GDELT, the news source it needed, was rate-limited
> to zero articles. That traceability, and being honest about what's still unproven, is what I think
> actually matters for a risk and ratings use case — not a flashier demo, but one you can audit."

**[End card: repo link, candidate name]**

---

## Timing budget check

| Segment | Duration | Cumulative |
|---|---|---|
| Intro | 0:30 | 0:30 |
| Setup/Run | 0:30 | 1:00 |
| Live Signal Feed | 0:30 | 1:30 |
| Audit Log | 0:30 | 2:00 |
| Stress Test | 0:50 | 2:50 |
| Scenario Explorer | 0:25 | 3:15 |
| Engine Quality | 0:30 | 3:45 |
| Results & limitations | 0:45 | 4:30 |
| **Buffer** | **0:30** | **5:00** |

## Numbers used in this script — checklist, source-checked

| Number as spoken | Source file | Field |
|---|---|---|
| 76 signals | `results/signals.jsonl` | row count |
| 3 fired (of 76 evaluated) | `results/stress_test_output.json` | `n_fired` / `n_signals_evaluated` |
| Sentiment < 0 gate (2 positive signals had fired before the fix) | `docs/ASSUMPTIONS.md` | "Module B: stress tests only fire on adverse signals" |
| $658.5M → $644.7M | `results/stress_test_output.json` | `headline_scenario.total_value_before` / `.total_value_after` |
| $13.79M / 2.09% stressed loss | `results/stress_test_output.json` | `headline_scenario.total_stressed_loss` / `.total_stressed_loss_pct` |
| +$1.3M MTM / $15.1M credit loss | `results/stress_test_output.json` | `headline_scenario.mtm_pnl` / `.credit_loss_on_loans` |
| Fed severely-adverse scenario | `results/stress_test_output.json` | `headline_scenario.tier` = `fed_severely_adverse` |
| FinBERT 0.660 / VADER 0.453 / majority 0.267 macro-F1 | `results/metrics.json` | `sentiment_eval.{finbert,vader,majority_baseline}.macro_f1` |
| Event classification 88.5% vs 84.0% baseline | `results/metrics.json` | `event_classification_eval.accuracy` / `.majority_baseline.accuracy` |
| Macroeconomic: 100% precision, 34% recall | `results/metrics.json` | `event_classification_eval.per_class.Macroeconomic` |
| Credit Event / Geopolitical: too few examples | `results/metrics.json` | `event_classification_eval.per_class.{Credit Event, Geopolitical}.support` (1 and 2) |
| GDELT rate-limited, 0 articles; impact study not run | `results/metrics.json` | `impact_score_event_study.status` = `not_run` |

## Before recording

- [ ] Confirm `results/signals.jsonl` and `results/stress_test_output.json` still match the numbers above
      (re-run `scripts/refresh_local.ps1` first if you want freshly-refreshed market data instead of the
      current state).
- [ ] Confirm the headline scenario is still real (`n_fired` > 0 in `results/stress_test_output.json`) — if
      it's gone to zero, adjust the Stress Test section's spoken lines or re-run the pipeline.
- [ ] Time a full dry run before recording for real — target ≤5:00, this script budgets to 4:30 with 30s
      slack, but actual delivery pace will vary.
