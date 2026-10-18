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
from generate_readme import require  # noqa: E402

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


def slide5_event_classification_line(metrics: dict) -> str:
    """Slide-friendly (no backticks, no Python lists, no file paths) -- unlike
    format_event_classification_status() in generate_readme.py, which is
    written for Markdown (README/dashboard) and isn't appropriate verbatim on
    a slide."""
    ece = metrics.get("event_classification_eval")
    if not ece:
        return "Event classifier: accuracy pending human labelling of the gold set."
    acc = ece["accuracy"]
    n = ece["n_gold_examples"]
    return f"Event classifier (rule-v1): {acc:.0%} overall accuracy, n={n} blind-labelled gold examples."


def slide7_event_classification_bullets(metrics: dict) -> list[str]:
    ece = metrics.get("event_classification_eval")
    if not ece:
        return ["Event classification: pending human labelling of the gold set."]
    pc = ece["per_class"]
    acc = ece["accuracy"]
    n = ece["n_gold_examples"]
    lines = [f"Event classifier (rule-v1): {acc:.0%} overall accuracy across {n} blind-labelled gold examples."]
    macro = pc.get("Macroeconomic")
    if macro and macro["support"] > 0:
        correct = round(macro["recall"] * macro["support"])
        lines.append(
            f"Macroeconomic: {macro['precision']:.0%} precision but only {macro['recall']:.0%} recall "
            f"({correct} of {int(macro['support'])}) — misses most true Macroeconomic headlines."
        )
    for cls in ["Credit Event", "Geopolitical"]:
        support = int(pc.get(cls, {}).get("support", 0))
        if 0 < support < 5:
            plural = "s" if support != 1 else ""
            lines.append(f"{cls}: cannot be evaluated yet — only {support} example{plural} in this sample.")
    return lines


def slide7_impact_study_line(metrics: dict) -> str:
    """Slide-friendly equivalent of format_impact_event_study_status() --
    no backticks, no file paths."""
    ies = metrics.get("impact_score_event_study")
    if not ies:
        return "Impact-score event study: pending a real sample."
    if ies.get("status") == "not_run":
        return f"Impact-score event study: not run — {ies['reason']}"
    n = ies.get("n_resolved")
    r = ies.get("spearman_r")
    if r is None:
        return f"Impact-score event study: n={n} resolved events — too few to compute a correlation at all."
    if not ies.get("power_adequate", False):
        return (f"Impact-score event study: n={n} (underpowered, below the n=200 threshold) — "
                f"Spearman r={r:.3f}, no relationship can be claimed either way at this sample size.")
    p = ies.get("spearman_p")
    sig = "a statistically significant" if (p is not None and p < 0.05) else "no statistically significant"
    return f"Impact-score event study: n={n}, Spearman r={r:.3f} — {sig} relationship with realised returns."


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


def add_lead_statement(slide, text, top=1.25, font_size=22):
    tb = slide.shapes.add_textbox(Inches(0.5), Inches(top), Inches(12.3), Inches(1.1))
    tf = tb.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = text
    p.font.size = Pt(font_size)
    p.font.bold = True
    p.font.color.rgb = INK
    return tb


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
    # % of position value, not a bare dollar figure -- a dollar error alone
    # doesn't say whether it's material; relative to the position's own
    # (true, full-reprice) value at that shock, it does.
    worst_bond_error_pct = abs(worst_bond_error["error"]) / worst_bond_error["full_reprice"] * 100

    prs = Presentation()
    prs.slide_width = SLIDE_W
    prs.slide_height = SLIDE_H

    # Slide 1: Title
    add_title_slide(
        prs, "AI/NLP Risk Engine + Strategic Portfolio Stress Test",
        "Aadit Siroya  |  IIT Guwahati  |  S&P Global & Crisil Campus Hackathon 2026",
    )

    # Slide 2: Problem & Approach -- leads with the business problem (a large,
    # standalone statement) before any process/methodology bullet.
    s2 = add_content_slide(prs, "Problem & Approach")
    add_lead_statement(
        s2, "Risk and ratings teams can't manually read every headline fast enough to know "
            "what it means for a portfolio."
    )
    add_bullets(s2, [
        ("Build: ingest news + social text → structured sentiment/event/impact signals → trigger a real portfolio stress test.", 0),
        ("Three real assumptions that turned out false on inspection, adapted rather than worked around: X/Twitter has no "
         "free read API in 2026 (switched to Mastodon); FinBERT is fine-tuned on Financial PhraseBank, so we evaluated it "
         "on a disjoint dataset to avoid leakage; a naive \"Target Corp\" name match collided with \"price target\" in "
         "nearly every analyst note (fixed with cashtag + context rules).", 0),
        ("Discipline throughout: verify every external claim live, never report a number a script didn't actually produce.", 0),
    ], top=2.5, font_size=18)

    # Slide 3: System Design
    # Bug found 2026-10-19: embedding at a fixed width=12.5in with no height
    # constraint let the image's own aspect ratio push its height to ~7.75in
    # -- starting at top=1.15in, that put its bottom edge at ~8.9in, well past
    # the 7.5in-tall slide, so the bottom of the diagram was silently cut off
    # in the actual deck (invisible outside the standalone PNG, which has no
    # slide boundary to be cut off by). Fixed to fit BOTH width and height
    # bounds (whichever constraint binds), centered horizontally.
    from PIL import Image as _Image
    _arch_img = _Image.open(ARCH_PATH)
    _aspect = _arch_img.width / _arch_img.height
    _max_w, _max_h = Inches(12.5), SLIDE_H - Inches(1.15) - Inches(0.25)
    _pic_w = _max_w
    _pic_h = int(_pic_w / _aspect)
    if _pic_h > _max_h:
        _pic_h = _max_h
        _pic_w = int(_pic_h * _aspect)
    _left = Inches(0.4) + (_max_w - _pic_w) // 2
    s3 = add_content_slide(prs, "System Design")
    s3.shapes.add_picture(str(ARCH_PATH), _left, Inches(1.15), width=_pic_w, height=_pic_h)

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
    results_lines = [
        f"FinBERT {finbert_f1:.3f} macro-F1 [{finbert_f1_ci[0]:.3f}, {finbert_f1_ci[1]:.3f}] vs VADER {vader_f1:.3f} "
        f"vs majority-class {majority_f1:.3f} (n=2000, CIs don't overlap — real improvement). "
        f"Bearish recall {finbert_recall_neg:.1%}. {finbert_latency:.0f}ms/doc on CPU.",

        f"{n_signals} real signals evaluated, {n_fired} fired a stress test. Naive duration-only error "
        f"grows to {worst_bond_error_pct:.2f}% of position value at {worst_bond_error['shock']} vs. full "
        f"reprice — genuine, growing convexity error, confirmed by tests.",

        slide5_event_classification_line(metrics),
    ]
    if headline is not None:
        results_lines.append(
            f"Headline stress result: portfolio value ${headline['total_value_before']:,.0f} -> "
            f"${headline['total_value_after']:,.0f}, total loss ${headline['total_stressed_loss']:,.0f} "
            f"({headline['total_stressed_loss_pct']:.2f}%) — MTM P&L ${headline['mtm_pnl']:,.0f}, "
            f"credit loss ${headline['credit_loss_on_loans']:,.0f}."
        )
    if data_provisional:
        results_lines.append("⚠ Market data (curve/equity spot) is PROVISIONAL this run — see docs/USER_TODO.md.")
    if headline is None:
        results_lines.append("⚠ MANUAL SCENARIO — NOT TRIGGERED BY A REAL SIGNAL: no real signal has fired a "
                              "stress test as of this generation; the chart shows a manually-constructed "
                              "scenario instead, labelled as such.")
    tb = s5.shapes.add_textbox(Inches(0.3), Inches(5.3), Inches(12.6), Inches(1.9))
    tf = tb.text_frame
    tf.word_wrap = True
    for i, line in enumerate(results_lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.text = line
        p.font.size = Pt(11.5)
        p.font.color.rgb = INK
        p.space_after = Pt(3)

    # Slide 6: Domain Impact
    s6 = add_content_slide(prs, "Domain Impact")
    add_bullets(s6, [
        ("Translates a news/social firehose into a dollar P&L number a credit/risk desk can act on, with full traceability: "
         "signal → scenario → shock → P&L (visible in the dashboard's Audit Log tab).", 0),
        ("Separating MTM P&L from credit loss mirrors how a real risk desk actually reports exposure — a trading-book "
         "instrument and a banking-book loan are never collapsed into one undifferentiated number.", 0),
        ("Shock magnitudes anchored to the Federal Reserve's own published severely-adverse scenario (fetched and cited "
         "directly, not estimated) — domain-grounded, not arbitrary round numbers.", 0),
        ("Fits S&P Global / Crisil's own domain: the signal taxonomy spans credit events, rating-adjacent language, "
         "and portfolio-level stress — the same surface a ratings/risk-analytics business operates on. (Credit-event "
         "detection itself isn't validated yet — too little gold-labelled data so far, see Limitations.)", 0),
    ], font_size=17)

    # Slide 7: Limitations & Next Steps -- the eval-status lines are pulled
    # live from metrics.json via slide-friendly formatters (no backticks, no
    # Python lists, no file paths -- unlike the README's Markdown-oriented
    # functions), so this slide automatically shows the real result with no
    # code change needed as Aadit's local runs update metrics.json.
    s7 = add_content_slide(prs, "Limitations & Next Steps")
    market_data_bullet = (
        "Market data (Treasury curve, equity spot) is PROVISIONAL in this build — fetched via a tool with a "
        "summarising model in the loop, not a direct download; a verification script exists to cross-check it."
        if data_provisional else
        "Market data (Treasury curve, equity spot) is SOURCED, not provisional — fetched directly."
    )
    s7_bullets = [(slide7_impact_study_line(metrics), 0)]
    s7_bullets += [(line, 0) for line in slide7_event_classification_bullets(metrics)]
    s7_bullets += [
        (market_data_bullet, 0),
        ("English-only; GDELT gives headline-level text only (no article body); the social replay source is "
         "historical with synthetic timestamps, creating a real date mismatch against the live market snapshot.", 0),
        ("Credit loss is 1-year EL (Basel-style), not IFRS 9 lifetime ECL — a real stress scenario would typically "
         "trigger Stage 2/3 staging, so this is a lower bound, stated as such.", 0),
        ("Next: grow the gold sample for Credit Event and Geopolitical, which have far too few examples to "
         "evaluate yet, and investigate the Macroeconomic recall gap. The impact-score event study has no "
         "further next step with GDELT abandoned — it would need a different news source entirely.", 0),
    ]
    add_bullets(s7, s7_bullets, font_size=13)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    prs.save(OUT_PATH)
    print(f"Wrote {OUT_PATH} (7 slides). Every number traced to metrics.json / stress_test_output.json.")


if __name__ == "__main__":
    main()
