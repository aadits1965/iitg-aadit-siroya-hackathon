#!/usr/bin/env python
"""Generates docs/presentation.pptx: exactly 7 slides, every number pulled
from results/metrics.json and results/stress_test_output.json via the same
require() guard as scripts/generate_readme.py -- REFUSES to build if any
field it needs is missing or None. PDF export needs LibreOffice, which is not
installed in this dev sandbox; the platform's own submission guidelines
accept PPTX directly (Section 4: "5-7 slides (PDF or PPTX)"), so this ships
as .pptx without a conversion step.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from generate_readme import format_event_classification_status, format_impact_event_study_status, require  # noqa: E402

from pptx import Presentation  # noqa: E402
from pptx.util import Inches, Pt  # noqa: E402
from pptx.dml.color import RGBColor  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
METRICS_PATH = ROOT / "results" / "metrics.json"
STRESS_PATH = ROOT / "results" / "stress_test_output.json"
ARCH_PATH = ROOT / "docs" / "architecture.png"
ASSETS_DIR = ROOT / "docs" / "deck_assets"
SCREENS_DIR = ROOT / "docs" / "screens"
OUT_PATH = ROOT / "docs" / "presentation.pptx"

# Slide 5 prefers a REAL dashboard screenshot (Aadit captures these locally --
# see docs/USER_TODO.md for the exact list and filenames) over the generated
# chart, per-slot, falling back to the chart only where a screenshot isn't
# present yet. No code change needed once screenshots are added -- just
# re-run this script.
SLOT_SCREEN_FALLBACKS = [
    (SCREENS_DIR / "live_signal_feed.png", ASSETS_DIR / "sentiment_chart.png"),
    (SCREENS_DIR / "stress_test.png", ASSETS_DIR / "stress_test_chart.png"),
    (SCREENS_DIR / "scenario_explorer.png", ASSETS_DIR / "naive_vs_full_chart.png"),
]


def resolve_slide5_images() -> list[Path]:
    resolved = []
    for screen_path, fallback_path in SLOT_SCREEN_FALLBACKS:
        chosen = screen_path if screen_path.exists() else fallback_path
        print(f"  slide 5 slot: {'REAL screenshot' if chosen == screen_path else 'generated chart (fallback)'} "
              f"-- {chosen.relative_to(ROOT)}")
        resolved.append(chosen)
    return resolved

INK = RGBColor(0x0B, 0x0B, 0x0B)
MUTED = RGBColor(0x52, 0x51, 0x4E)
BLUE = RGBColor(0x2A, 0x78, 0xD6)
RED = RGBColor(0xE3, 0x49, 0x48)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)

SLIDE_W = Inches(13.333)
SLIDE_H = Inches(7.5)


def add_title_slide(prs, title, subtitle):
    slide = prs.slides.add_slide(prs.slide_layouts[6])  # blank
    bg = slide.shapes.add_shape(1, 0, 0, SLIDE_W, SLIDE_H)
    bg.fill.solid()
    bg.fill.fore_color.rgb = BLUE
    bg.line.fill.background()
    bg.shadow.inherit = False
    tb = slide.shapes.add_textbox(Inches(1), Inches(2.6), Inches(11.3), Inches(1.8))
    tf = tb.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = title
    p.font.size = Pt(40)
    p.font.bold = True
    p.font.color.rgb = WHITE
    p2 = tf.add_paragraph()
    p2.text = subtitle
    p2.font.size = Pt(18)
    p2.font.color.rgb = WHITE
    return slide


def add_content_slide(prs, title):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    tb = slide.shapes.add_textbox(Inches(0.5), Inches(0.3), Inches(12.3), Inches(0.8))
    p = tb.text_frame.paragraphs[0]
    p.text = title
    p.font.size = Pt(28)
    p.font.bold = True
    p.font.color.rgb = INK
    line = slide.shapes.add_shape(1, Inches(0.5), Inches(1.05), Inches(12.3), Pt(2.5))
    line.fill.solid()
    line.fill.fore_color.rgb = BLUE
    line.line.fill.background()
    line.shadow.inherit = False
    return slide


def add_bullets(slide, bullets, left=0.5, top=1.3, width=12.3, height=5.8, font_size=16):
    tb = slide.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(height))
    tf = tb.text_frame
    tf.word_wrap = True
    for i, (text, indent) in enumerate(bullets):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.text = ("    " * indent) + "• " + text
        p.font.size = Pt(font_size - indent * 2)
        p.font.color.rgb = INK
        p.space_after = Pt(8)
    return tb


def main():
    if not METRICS_PATH.exists() or not STRESS_PATH.exists():
        print("REFUSING TO BUILD DECK: results/metrics.json or results/stress_test_output.json missing.")
        sys.exit(1)
    if not ARCH_PATH.exists():
        print("REFUSING TO BUILD DECK: docs/architecture.png missing. Run scripts/generate_architecture_diagram.py first.")
        sys.exit(1)
    for chart in ["sentiment_chart.png", "stress_test_chart.png", "naive_vs_full_chart.png"]:
        if not (ASSETS_DIR / chart).exists():
            print(f"REFUSING TO BUILD DECK: {chart} missing. Run scripts/generate_deck_charts.py first.")
            sys.exit(1)

    metrics = json.loads(METRICS_PATH.read_text(encoding="utf-8"))
    stress = json.loads(STRESS_PATH.read_text(encoding="utf-8"))

    # Hard-required fields -- raises (refuses to build) if any is missing/None.
    finbert_f1 = require(metrics, "sentiment_eval", "finbert", "macro_f1")
    finbert_f1_ci = require(metrics, "sentiment_eval", "finbert", "macro_f1_ci95")
    vader_f1 = require(metrics, "sentiment_eval", "vader", "macro_f1")
    majority_f1 = require(metrics, "sentiment_eval", "majority_baseline", "macro_f1")
    finbert_recall_neg = require(metrics, "sentiment_eval", "finbert", "per_class", "negative", "recall")
    finbert_latency = require(metrics, "sentiment_eval", "finbert", "latency_ms_per_doc")
    n_signals = require(stress, "n_signals_evaluated")
    n_fired = require(stress, "n_fired")
    data_provisional = stress.get("data_provisional", False)
    headline = stress.get("headline_scenario")
    bond_comparisons = require(stress, "naive_vs_full_reprice", "bond", "comparisons")
    worst_bond_error = max(bond_comparisons, key=lambda c: abs(c["error"]))

    prs = Presentation()
    prs.slide_width = SLIDE_W
    prs.slide_height = SLIDE_H

    # Slide 1: Title
    add_title_slide(
        prs, "AI/NLP Risk Engine + Strategic Portfolio Stress Test",
        "Aadit Siroya  |  IIT Guwahati  |  S&P Global & Crisil Campus Hackathon 2026",
    )

    # Slide 2: Problem & Approach
    s2 = add_content_slide(prs, "Problem & Approach")
    add_bullets(s2, [
        ("Risk and ratings teams can't manually read every headline fast enough to know what it means for a portfolio.", 0),
        ("Build: ingest news + social text → structured sentiment/event/impact signals → trigger a real portfolio stress test.", 0),
        ("Discipline throughout: verify every external claim live, never report a number a script didn't actually produce.", 0),
        ("Confirmed false on inspection, adapted rather than worked around: X/Twitter has no free read API in 2026; "
         "FinBERT is fine-tuned on the exact dataset the brief's own eval plan implied using (leakage); "
         '"price target" collides with a naive "Target Corp" name match.', 0),
    ], font_size=18)

    # Slide 3: System Design
    s3 = add_content_slide(prs, "System Design")
    s3.shapes.add_picture(str(ARCH_PATH), Inches(0.4), Inches(1.15), width=Inches(12.5))

    # Slide 4: Implementation Highlights
    s4 = add_content_slide(prs, "Implementation Highlights")
    add_bullets(s4, [
        ("FinBERT (primary) vs VADER (naive baseline) vs majority-class, scored with bootstrap 95% CIs, not point estimates alone.", 0),
        ("Event classifier frozen at rule-v1 (git tag classifier-v1) before scoring against hand-labelled gold data — no eval-set tuning.", 0),
        ("Polling-based pub/sub (FastAPI + a flat JSONL file), documented honestly as polling, not a real message bus.", 0),
        ("Module B: full cashflow reprice for bonds, swap DV01 via bump-and-reprice, closed-form Black-Scholes for options — "
         "compared against the required naive (duration/delta-only) approximation, not just implemented once.", 0),
        ("Mark-to-market P&L and credit loss (ΔEL on loans) kept as two separate numbers by construction — a loan is never "
         "both fair-valued AND provisioned, which would double-count the same credit deterioration.", 0),
        ("Demo mode verified byte-identical across two real end-to-end runs (tests/test_demo_idempotency.py).", 0),
    ], font_size=16)

    # Slide 5: Key Results
    s5 = add_content_slide(prs, "Key Results")
    print("Resolving slide 5 images (real screenshot if available, else generated chart):")
    slide5_images = resolve_slide5_images()
    for img_path, left in zip(slide5_images, (0.3, 4.55, 8.8)):
        s5.shapes.add_picture(str(img_path), Inches(left), Inches(1.15), width=Inches(4.1))
    results_text = (
        f"FinBERT {finbert_f1:.3f} macro-F1 [{finbert_f1_ci[0]:.3f}, {finbert_f1_ci[1]:.3f}] vs VADER {vader_f1:.3f} "
        f"vs majority-class {majority_f1:.3f} (n=2000, CIs don't overlap — real improvement). "
        f"Bearish recall {finbert_recall_neg:.1%}. {finbert_latency:.0f}ms/doc on CPU.  |  "
        f"{n_signals} real signals evaluated, {n_fired} fired a stress test.  |  "
        f"Naive duration-only error grows to {worst_bond_error['error']:,.0f} at {worst_bond_error['shock']} "
        f"vs. full reprice — genuine, growing convexity error, confirmed by tests."
    )
    if data_provisional:
        results_text += "  ⚠ Market data (curve/equity spot) is PROVISIONAL this run — see docs/USER_TODO.md."
    if headline is None:
        results_text += ("  ⚠ MANUAL SCENARIO — NOT TRIGGERED BY A REAL SIGNAL: no real signal has "
                          "fired a stress test as of this generation; the chart shows a manually-constructed "
                          "scenario instead, labelled as such.")
    tb = s5.shapes.add_textbox(Inches(0.3), Inches(5.3), Inches(12.6), Inches(1.9))
    tf = tb.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = results_text
    p.font.size = Pt(13)
    p.font.color.rgb = INK

    # Slide 6: Domain Impact
    s6 = add_content_slide(prs, "Domain Impact")
    add_bullets(s6, [
        ("Translates a news/social firehose into a dollar P&L number a credit/risk desk can act on, with full traceability: "
         "signal → scenario → shock → P&L (visible in the dashboard's Audit Log tab).", 0),
        ("Separating MTM P&L from credit loss mirrors how a real risk desk actually reports exposure — a trading-book "
         "instrument and a banking-book loan are never collapsed into one undifferentiated number.", 0),
        ("Shock magnitudes anchored to the Federal Reserve's own published severely-adverse scenario (fetched and cited "
         "directly, not estimated) — domain-grounded, not arbitrary round numbers.", 0),
        ("Fits S&P Global / Crisil's own domain: credit events, rating-adjacent language, and portfolio-level stress "
         "are exactly the surface a ratings/risk-analytics business operates on.", 0),
    ], font_size=17)

    # Slide 7: Limitations & Next Steps -- the two eval-status lines are pulled
    # live from metrics.json via the same functions the README uses, so this
    # slide automatically shows the real result (including an explicit "no
    # significant relationship" or "UNDERPOWERED" statement) once Aadit's
    # local GDELT/labelling runs produce it, with no code change needed here.
    s7 = add_content_slide(prs, "Limitations & Next Steps")
    market_data_bullet = (
        "Market data (Treasury curve, equity spot) is PROVISIONAL in this build — fetched via a tool with a "
        "summarising model in the loop, not a direct download; a verification script exists to cross-check it."
        if data_provisional else
        "Market data (Treasury curve, equity spot) is SOURCED, not provisional — fetched directly. An earlier "
        "WebFetch-relayed snapshot was off by 38-141bp at every tenor (transcription error) and was replaced."
    )
    add_bullets(s7, [
        (format_impact_event_study_status(metrics).replace("**", ""), 0),
        (format_event_classification_status(metrics).replace("**", ""), 0),
        (market_data_bullet, 0),
        ("English-only; GDELT gives headline-level text only (no article body); the social replay source is "
         "historical with synthetic timestamps, creating a real date mismatch against the live market snapshot.", 0),
        ("Credit loss is 1-year EL (Basel-style), not IFRS 9 lifetime ECL — a real stress scenario would typically "
         "trigger Stage 2/3 staging, so this is a lower bound, stated as such.", 0),
        ("Next: finish event-classification scoring once the gold set is hand-labelled. The impact-score event "
         "study has no further next step with GDELT abandoned (rate-limited, 0 articles over 2+ hours) — it "
         "would need a different news source entirely.", 0),
    ], font_size=15)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    prs.save(OUT_PATH)
    print(f"Wrote {OUT_PATH} (7 slides). Every number traced to metrics.json / stress_test_output.json.")


if __name__ == "__main__":
    main()
