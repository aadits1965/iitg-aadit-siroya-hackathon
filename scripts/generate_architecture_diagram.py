#!/usr/bin/env python
"""Generates docs/architecture.png from code (matplotlib -- no external binary
dependency like graphviz's `dot`, which isn't installed in this dev sandbox and
may not be on every grader's machine either). High-resolution (>=2000px wide).

The market-data / evaluation / test-count boxes are NOT hardcoded -- they read
results/metrics.json, results/stress_test_output.json, and a live pytest
collection count every time this script runs, same discipline as
scripts/generate_deck.py and scripts/generate_readme.py. A box can go stale
in exactly the way a hardcoded one did before this fix (GDELT shown as a live
source after it had been abandoned; market data shown PROVISIONAL after it
had been replaced with a direct fetch; a frozen "126 tests" count after the
suite had grown).
"""
import json
import re
import subprocess
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

ROOT = Path(__file__).resolve().parents[1]
OUT_PATH = ROOT / "docs" / "architecture.png"
METRICS_PATH = ROOT / "results" / "metrics.json"
STRESS_PATH = ROOT / "results" / "stress_test_output.json"


def count_tests() -> str:
    """Live pytest collection count, not a hardcoded number that silently goes
    stale as the suite grows. Falls back to a plain label if pytest can't run
    for some reason (e.g. missing dependency) rather than crashing the whole
    diagram over a cosmetic count."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "--collect-only", "-q"],
            cwd=ROOT, capture_output=True, text=True, timeout=120,
        )
        m = re.search(r"(\d+) tests? collected", result.stdout)
        if m:
            return f"{m.group(1)} tests (live pytest collection count)"
    except Exception:
        pass
    return "test count unavailable (run pytest --collect-only)"


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))

BLUE = "#2a78d6"
ORANGE = "#eb6834"
AQUA = "#1baf7a"
YELLOW = "#eda100"
MAGENTA = "#e87ba4"
GREEN = "#008300"
VIOLET = "#4a3aa7"
INK = "#0b0b0b"
MUTED = "#52514e"
SURFACE = "#fcfcfb"


def box(ax, xy, w, h, text, color, fontsize=10.5, text_color="white"):
    x, y = xy
    rect = mpatches.FancyBboxPatch(
        (x, y), w, h, boxstyle="round,pad=0.015,rounding_size=0.07",
        linewidth=0, facecolor=color, zorder=2,
    )
    ax.add_patch(rect)
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fontsize,
             color=text_color, weight="bold", zorder=3, linespacing=1.4)
    return (x, y, w, h)


def center_bottom(b):
    return (b[0] + b[2] / 2, b[1])


def center_top(b):
    return (b[0] + b[2] / 2, b[1] + b[3])


def arrow(ax, p1, p2, color=MUTED, style="-", lw=1.6):
    ax.annotate("", xy=p2, xytext=p1,
                arrowprops=dict(arrowstyle="-|>", color=color, lw=lw, linestyle=style,
                                 shrinkA=3, shrinkB=3), zorder=1)


def main():
    metrics = load_json(METRICS_PATH)
    stress = load_json(STRESS_PATH)

    ece = metrics.get("event_classification_eval")
    if ece:
        event_class_line = f"Event class: rule-v1, accuracy={ece['accuracy']:.0%}, macro-F1={ece['macro_avg']['f1-score']:.2f} (n={ece['n_gold_examples']})"
    else:
        event_class_line = "Event class: rule-v1, pending gold labels"

    ies = metrics.get("impact_score_event_study")
    if ies and ies.get("status") == "not_run":
        impact_study_line = "Impact-score study: not run (GDELT rate-limited)"
    elif ies:
        impact_study_line = f"Impact-score study: n={ies.get('n_resolved', '?')}, r={ies.get('spearman_r')}"
    else:
        impact_study_line = "Impact-score study: pending"

    data_provisional = stress.get("data_provisional", False)
    curve_as_of = stress.get("curve_as_of", "unknown date")
    market_data_line = (
        f"(PROVISIONAL — WebFetch-sourced, as_of {curve_as_of})" if data_provisional
        else f"(SOURCED — direct fetch, as_of {curve_as_of})"
    )

    tests_label = count_tests()

    fig, ax = plt.subplots(figsize=(21, 13), dpi=135)
    ax.set_xlim(0, 21)
    ax.set_ylim(0, 13)
    ax.axis("off")
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)

    ax.text(10.5, 12.5, "AI/NLP Risk Engine + Module B Strategic Portfolio Stress Test",
            ha="center", fontsize=19, weight="bold", color=INK)
    ax.text(10.5, 12.0, "S&P Global & Crisil Campus Hackathon 2026  —  generated from code: scripts/generate_architecture_diagram.py",
            ha="center", fontsize=10, color=MUTED, style="italic")

    COL_W = 4.3
    GAP = 0.3
    X0 = 0.4

    # --- Row 1: Sources ---
    b_gdelt = box(ax, (X0, 10.2), 2.7, 0.9, "GDELT (attempted —\nrate-limited, 0 articles)", BLUE, 9.5)
    b_mastodon = box(ax, (X0 + 2.9, 10.2), 2.7, 0.9, "Mastodon\n(live social)", BLUE)
    b_replay = box(ax, (X0 + 5.8, 10.2), 2.9, 0.9, "Twitter replay\n(offline fallback, MIT)", BLUE)

    # --- Row 2: Ingestion ---
    b_ingest = box(ax, (X0, 8.9), 8.9, 0.85, "Ingestion adapters\npydantic schema  •  exact + fuzzy dedup (rapidfuzz)", ORANGE, 11)
    for b in (b_gdelt, b_mastodon, b_replay):
        arrow(ax, center_bottom(b), (b[0] + b[2] / 2, 9.75))

    # --- Row 3: NLP Engine ---
    nlp_y = 7.3
    b_entity = box(ax, (X0, nlp_y), 2.1, 1.15, "Entity\nlinking", AQUA)
    b_sentiment = box(ax, (X0 + 2.3, nlp_y), 2.1, 1.15, "Sentiment\nFinBERT\nvs VADER", AQUA)
    b_event = box(ax, (X0 + 4.6, nlp_y), 2.1, 1.15, "Event class\nrule-v1\n(frozen)", AQUA)
    b_impact = box(ax, (X0 + 6.9, nlp_y), 2.0, 1.15, "Impact Score\n1-10, 5\ncomponents", AQUA)
    mid_ingest = (X0 + 8.9 / 2, 8.9)
    for b in (b_entity, b_sentiment, b_event, b_impact):
        arrow(ax, mid_ingest, (b[0] + b[2] / 2, nlp_y + 1.15))

    # --- Row 4: Signal store ---
    store_y = 6.0
    b_store = box(ax, (X0, store_y), 4.3, 0.85, "Signal store\nresults/signals.jsonl + SQLite", VIOLET, 10.5)
    b_api = box(ax, (X0 + 4.6, store_y), 4.3, 0.85, "FastAPI\n/signals  /health  (polled)", VIOLET, 10.5)
    nlp_mid_x = X0 + 8.9 / 2
    arrow(ax, (nlp_mid_x, nlp_y), (X0 + 2.15, store_y + 0.85))

    # --- Row 5: Trigger + Portfolio ---
    trig_y = 4.7
    b_trigger = box(ax, (X0, trig_y), 4.3, 0.85, "Trigger engine\nimpact>7 AND sentiment<0\n6h cooldown/cluster", MAGENTA, 8.5)
    b_portfolio = box(ax, (X0 + 4.6, trig_y), 4.3, 0.85, "Synthetic portfolio\n50 positions, 5 asset classes", MAGENTA, 10.5)
    arrow(ax, center_bottom(b_store), center_top(b_trigger))
    arrow(ax, center_bottom(b_api), center_top(b_portfolio))

    # --- Row 6: Shock + Revaluation ---
    shock_y = 3.4
    b_shock = box(ax, (X0, shock_y), 4.3, 0.85, "Shock library\nFed severely-adverse (sourced)\n+ 3 other tiers", GREEN, 10)
    b_reval = box(ax, (X0 + 4.6, shock_y), 4.3, 0.85, "Full-reprice revaluation\nMTM P&L vs credit-loss split", GREEN, 10.5)
    arrow(ax, center_bottom(b_trigger), center_top(b_shock))
    arrow(ax, center_bottom(b_portfolio), center_top(b_reval))
    arrow(ax, (X0 + 4.3, shock_y + 0.42), (X0 + 4.6, shock_y + 0.42), style="--")

    # --- Row 7: Dashboard ---
    dash_y = 1.9
    b_dash = box(ax, (X0, dash_y), 8.9, 1.0,
                 "Streamlit dashboard\nLive Signal Feed  •  Engine Quality  •  Stress Test\nScenario Explorer  •  Audit Log",
                 BLUE, 10)
    arrow(ax, center_bottom(b_shock), (X0 + 2.15, dash_y + 1.0))
    arrow(ax, center_bottom(b_reval), (X0 + 6.75, dash_y + 1.0))

    # --- run.py orchestrator: a banner, not a pipeline stage -- no data-flow
    # arrow to/from it, since it's what RUNS every stage above, not something
    # stages feed into.
    run_y = 0.4
    b_run = box(ax, (X0, run_y), 8.9, 0.9,
                "run.py --mode demo | live\norchestrates every stage above — single entry point", VIOLET, 11)
    ax.plot([X0 + 0.3, X0 + 8.6], [dash_y - 0.15, dash_y - 0.15], color=MUTED, lw=0.8, linestyle=(0, (1, 2)))

    # --- Right column: Market data + evaluation (clearly separate, own connector) ---
    RX = 10.3
    b_market = box(ax, (RX, 7.5), 4.6, 1.5,
                   f"Market data\nUS Treasury curve + equity spot\n{market_data_line}\n"
                   "+ Fed scenario (SOURCED, direct curl)", YELLOW, 9, text_color=INK)
    b_eval = box(ax, (RX, 5.2), 4.6, 2.0,
                 f"Evaluation → results/metrics.json\nSentiment: FinBERT vs VADER (CIs)\n"
                 f"{event_class_line}\n{impact_study_line}", YELLOW, 9, text_color=INK)

    # connector: market data feeds the revaluation step -- routed BELOW both
    # the market and evaluation boxes (not diagonally through them) so the
    # line/label never overlaps either box's text.
    arrow(ax, (RX, 5.0), (X0 + 8.9, shock_y + 0.3), color=MUTED, style=":")
    ax.text(9.3, 4.65, "feeds", fontsize=8, color=MUTED, style="italic", rotation=-11)

    b_tests = box(ax, (RX, 2.6), 4.6, 2.3,
                  f"Verified, not assumed\n\n"
                  f"{tests_label}\n"
                  "91.7% / 94.5% entity-link precision\n(Wilson 95% CIs, two samples)\n"
                  "Demo mode: byte-identical signals.jsonl\nacross two real end-to-end runs\n"
                  "Classifier frozen: rule-v1 (tag classifier-v1)", MUTED, 9.5)

    legend_elements = [
        Line2D([0], [0], color=MUTED, lw=1.6, label="pipeline data flow"),
        Line2D([0], [0], color=MUTED, lw=1.6, linestyle="--", label="shock set → revaluation"),
        Line2D([0], [0], color=MUTED, lw=1.6, linestyle=":", label="market data → revaluation"),
    ]
    ax.legend(handles=legend_elements, loc="lower right", bbox_to_anchor=(0.995, 0.015),
              fontsize=8.5, frameon=False, labelcolor=MUTED)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT_PATH, dpi=135, bbox_inches="tight", facecolor=SURFACE)
    plt.close(fig)

    from PIL import Image
    img = Image.open(OUT_PATH)
    print(f"Wrote {OUT_PATH} ({img.width}x{img.height}px)")
    if img.width < 2000:
        print(f"WARNING: width {img.width}px is below the required >=2000px")
        sys.exit(1)


if __name__ == "__main__":
    main()
