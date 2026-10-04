#!/usr/bin/env python
"""Generates the chart images embedded in the deck, from the same real data
the dashboard reads (results/metrics.json, results/stress_test_output.json).
Not a dashboard screenshot -- this dev environment has no browser automation
tool available (no chromium-cli/Playwright installed, confirmed in Phase 5)
to capture one; these are real charts built from the real underlying data
instead, labelled as such in the deck, not presented as a screenshot.
"""
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
ASSETS_DIR = ROOT / "docs" / "deck_assets"
BLUE, ORANGE, AQUA, RED = "#2a78d6", "#eb6834", "#1baf7a", "#e34948"
MUTED, INK = "#52514e", "#0b0b0b"


def sentiment_chart(metrics: dict) -> Path:
    sent = metrics["sentiment_eval"]
    models = [("majority_baseline", "Majority\nclass", MUTED), ("vader", "VADER", ORANGE), ("finbert", "FinBERT", BLUE)]
    fig, ax = plt.subplots(figsize=(7, 4.2), dpi=150)
    for i, (key, label, color) in enumerate(models):
        r = sent[key]
        lo, hi = r["macro_f1_ci95"]
        ax.bar(i, r["macro_f1"], color=color, width=0.55,
               yerr=[[r["macro_f1"] - lo], [hi - r["macro_f1"]]], capsize=5,
               error_kw=dict(ecolor=INK, lw=1.3))
        ax.text(i, r["macro_f1"] + (hi - r["macro_f1"]) + 0.015, f"{r['macro_f1']:.3f}",
                ha="center", fontsize=10, weight="bold", color=INK)
    ax.set_xticks(range(len(models)))
    ax.set_xticklabels([m[1] for m in models], fontsize=10)
    ax.set_ylabel("Macro-F1 (95% bootstrap CI)", fontsize=10)
    ax.set_ylim(0, 0.85)
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_title(f"Sentiment: FinBERT vs baselines (n={sent['n_fetched']})", fontsize=11, weight="bold")
    fig.tight_layout()
    out = ASSETS_DIR / "sentiment_chart.png"
    fig.savefig(out, facecolor="white")
    plt.close(fig)
    return out


def stress_test_chart(stress: dict) -> Path:
    headline = stress.get("headline_scenario") or stress["illustrative_example_NOT_from_a_real_trigger"]
    pnl = headline["pnl_by_asset_class"]
    fig, ax = plt.subplots(figsize=(7, 4.2), dpi=150)
    colors = [BLUE if v >= 0 else RED for v in pnl.values()]
    ax.bar(list(pnl.keys()), list(pnl.values()), color=colors)
    ax.axhline(0, color=INK, lw=0.8)
    ax.set_ylabel("P&L ($)", fontsize=10)
    ax.spines[["top", "right"]].set_visible(False)
    is_real = "signal_id" in headline
    title = ("P&L by asset class — real triggered signal" if is_real
              else "P&L by asset class — MANUAL SCENARIO, not a real trigger")
    ax.set_title(title, fontsize=11, weight="bold")
    ax.ticklabel_format(style="plain", axis="y")
    for i, (k, v) in enumerate(pnl.items()):
        ax.text(i, v + (3e5 if v >= 0 else -8e5), f"${v:,.0f}", ha="center", fontsize=8)
    fig.tight_layout()
    out = ASSETS_DIR / "stress_test_chart.png"
    fig.savefig(out, facecolor="white")
    plt.close(fig)
    return out


def naive_vs_full_chart(stress: dict) -> Path:
    bond = sorted(stress["naive_vs_full_reprice"]["bond"]["comparisons"],
                  key=lambda c: int(c["shock"].replace("bp", "")))
    fig, ax = plt.subplots(figsize=(7, 4.2), dpi=150)
    shocks = [c["shock"] for c in bond]
    full = [c["full_reprice"] for c in bond]
    naive = [c["naive_duration_only"] for c in bond]
    ax.plot(shocks, full, "o-", color=BLUE, label="Full reprice", lw=2)
    ax.plot(shocks, naive, "s--", color=ORANGE, label="Duration-only (naive)", lw=2)
    ax.set_ylabel("Bond price ($)", fontsize=10)
    ax.set_title("Full reprice vs naive duration-only approximation", fontsize=11, weight="bold")
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(fontsize=9, frameon=False)
    fig.tight_layout()
    out = ASSETS_DIR / "naive_vs_full_chart.png"
    fig.savefig(out, facecolor="white")
    plt.close(fig)
    return out


def main():
    metrics_path = ROOT / "results" / "metrics.json"
    stress_path = ROOT / "results" / "stress_test_output.json"
    if not metrics_path.exists() or not stress_path.exists():
        print("REFUSING: results/metrics.json or results/stress_test_output.json missing.")
        sys.exit(1)

    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    stress = json.loads(stress_path.read_text(encoding="utf-8"))

    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    paths = [sentiment_chart(metrics), stress_test_chart(stress), naive_vs_full_chart(stress)]
    for p in paths:
        print(f"wrote {p}")


if __name__ == "__main__":
    main()
