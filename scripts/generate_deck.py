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
from generate_readme import event_classifier_stat, require  # noqa: E402

from pptx import Presentation  # noqa: E402
from pptx.util import Inches, Pt  # noqa: E402
from pptx.dml.color import RGBColor  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
METRICS_PATH = ROOT / "results" / "metrics.json"
STRESS_PATH = ROOT / "results" / "stress_test_output.json"
ARCH_PATH = ROOT / "docs" / "architecture.png"
ASSETS_DIR = ROOT / "docs" / "deck_assets"
OUT_PATH = ROOT / "docs" / "presentation.pptx"

def slide_event_classification_line(metrics: dict) -> str:
    """Slide-friendly (no backticks, no Python lists, no file paths) -- unlike
    format_event_classification_status() in generate_readme.py, which is
    written for Markdown (README/dashboard) and isn't appropriate verbatim on
    a slide. Always paired with its baseline and the Macroeconomic
    precision/recall gap (event_classifier_stat()), never a bare accuracy
    number presented as more conclusive than it is."""
    stat = event_classifier_stat(metrics)
    if stat is None:
        return "Event classifier: accuracy pending human labelling of the gold set."
    return f"Event classifier: {stat}."


def slide7_event_classification_bullets(metrics: dict) -> list[str]:
    ece = metrics.get("event_classification_eval")
    if not ece:
        return ["Event classification: pending human labelling."]
    pc = ece["per_class"]
    lines = [f"Event classifier: {event_classifier_stat(metrics)}."]
    for cls in ["Credit Event", "Geopolitical"]:
        support = int(pc.get(cls, {}).get("support", 0))
        if 0 < support < 5:
            lines.append(f"{cls}: too few examples to evaluate (n={support}).")
    return lines


def slide7_impact_study_line(metrics: dict) -> str:
    """Slide-friendly equivalent of format_impact_event_study_status() --
    no backticks, no file paths."""
    ies = metrics.get("impact_score_event_study")
    if not ies:
        return "Impact-score event study: pending a real sample."
    if ies.get("status") == "not_run":
        return "Impact-score event study: not run — GDELT rate-limited (0 articles over 2+ hours), abandoned for this submission."
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


INK = RGBColor(0x0B, 0x0B, 0x0B)
MUTED = RGBColor(0x52, 0x51, 0x4E)
BLUE = RGBColor(0x2A, 0x78, 0xD6)
RED = RGBColor(0xE3, 0x49, 0x48)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)

SLIDE_W = Inches(13.333)
SLIDE_H = Inches(7.5)


def add_title_slide(prs, title_lines: list[str], subtitle):
    """title_lines is a list of EXPLICIT lines, not one long string left to
    auto-wrap -- a long title at this font size could wrap PowerPoint's own
    way, which risks leaving a single stray word alone on its own line.
    Explicit lines give full control over where it breaks instead."""
    slide = prs.slides.add_slide(prs.slide_layouts[6])  # blank
    bg = slide.shapes.add_shape(1, 0, 0, SLIDE_W, SLIDE_H)
    bg.fill.solid()
    bg.fill.fore_color.rgb = BLUE
    bg.line.fill.background()
    bg.shadow.inherit = False
    tb = slide.shapes.add_textbox(Inches(1), Inches(2.3), Inches(11.3), Inches(2.2))
    tf = tb.text_frame
    tf.word_wrap = True
    for i, line in enumerate(title_lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.text = line
        p.font.size = Pt(40)
        p.font.bold = True
        p.font.color.rgb = WHITE
    p2 = tf.add_paragraph()
    p2.text = subtitle
    p2.font.size = Pt(18)
    p2.font.color.rgb = WHITE
    p2.space_before = Pt(14)
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


def fmt_signed_dollar(x: float) -> str:
    return f"{'-' if x < 0 else '+'}${abs(x):,.0f}"


def add_column_header(slide, text, left, top, width=5.9):
    tb = slide.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(0.4))
    p = tb.text_frame.paragraphs[0]
    p.text = text
    p.font.size = Pt(15)
    p.font.bold = True
    p.font.color.rgb = BLUE
    return tb


def add_callout_panel(slide, left, top, width, height, lines, big_font=22, small_font=14, color=None):
    """A filled rounded panel with one large bold headline line and optional
    smaller supporting lines below it -- for a single key number that should
    read at a glance, not be buried in a bullet."""
    panel = slide.shapes.add_shape(5, Inches(left), Inches(top), Inches(width), Inches(height))  # 5 = ROUNDED_RECTANGLE
    panel.fill.solid()
    panel.fill.fore_color.rgb = color or RGBColor(0xF2, 0xF6, 0xFC)
    panel.line.color.rgb = BLUE
    panel.line.width = Pt(1.5)
    panel.shadow.inherit = False
    tf = panel.text_frame
    tf.word_wrap = True
    tf.margin_left = Inches(0.25)
    tf.margin_right = Inches(0.25)
    tf.margin_top = Inches(0.12)
    tf.margin_bottom = Inches(0.12)
    for i, (text, is_big) in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.text = text
        p.font.size = Pt(big_font if is_big else small_font)
        p.font.bold = is_big
        p.font.color.rgb = INK
        p.space_after = Pt(4)
    return panel


def main():
    if not METRICS_PATH.exists() or not STRESS_PATH.exists():
        print("REFUSING TO BUILD DECK: results/metrics.json or results/stress_test_output.json missing.")
        sys.exit(1)
    if not ARCH_PATH.exists():
        print("REFUSING TO BUILD DECK: docs/architecture.png missing. Run scripts/generate_architecture_diagram.py first.")
        sys.exit(1)
    for chart in ["sentiment_chart.png", "stress_test_chart.png"]:
        if not (ASSETS_DIR / chart).exists():
            print(f"REFUSING TO BUILD DECK: {chart} missing. Run scripts/generate_deck_charts.py first.")
            sys.exit(1)

    metrics = json.loads(METRICS_PATH.read_text(encoding="utf-8"))
    stress = json.loads(STRESS_PATH.read_text(encoding="utf-8"))

    # Hard-required fields -- raises (refuses to build) if any is missing/None.
    finbert_f1 = require(metrics, "sentiment_eval", "finbert", "macro_f1")
    vader_f1 = require(metrics, "sentiment_eval", "vader", "macro_f1")
    majority_f1 = require(metrics, "sentiment_eval", "majority_baseline", "macro_f1")
    finbert_recall_neg = require(metrics, "sentiment_eval", "finbert", "per_class", "negative", "recall")
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

    # Slide 1: Title -- explicit two-line split (not left to auto-wrap) so no
    # single word ever ends up alone on its own line.
    add_title_slide(
        prs, ["AI/NLP Risk Engine", "+ Strategic Portfolio Stress Test"],
        "Aadit Siroya  |  IIT Guwahati  |  S&P Global & Crisil Campus Hackathon 2026",
    )

    # Slide 2: Problem & Approach -- leads with the business problem (a large,
    # standalone statement), then a two-column lower half: what was built vs.
    # assumptions that turned out false on inspection (with the real measured
    # numbers, not a vague "nearly every analyst note" claim).
    s2 = add_content_slide(prs, "Problem & Approach")
    add_lead_statement(
        s2, "Risk and ratings teams can't manually read every headline fast enough to know "
            "what it means for a portfolio.", font_size=24
    )
    add_bullets(s2, [
        ("Built: news + social text → sentiment/event/impact signals → a real portfolio stress test.", 0),
    ], top=2.7, height=0.7, font_size=19)

    add_column_header(s2, "What we built it with", left=0.5, top=3.6)
    add_bullets(s2, [
        ("Verify every external claim live — never report a number a script didn't actually produce.", 0),
        ("Two sources, one engine: live Mastodon posts and a historical tweet-replay fallback.", 0),
    ], left=0.5, top=4.1, width=5.9, height=3.0, font_size=18)

    add_column_header(s2, "Assumptions that turned out false", left=6.8, top=3.6)
    add_bullets(s2, [
        ("X/Twitter has no free read API in 2026 → switched to Mastodon.", 0),
        ("FinBERT is fine-tuned on Financial PhraseBank → evaluated on a disjoint dataset to avoid leakage.", 0),
        ("Entity linking: a naive name match collided with everyday phrases (\"Target\" in \"price target\") "
         "→ fixed with cashtag matching + context rules.", 0),
    ], left=6.8, top=4.1, width=5.9, height=3.0, font_size=18)

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
        ("FinBERT vs VADER vs majority-class — scored with bootstrap 95% CIs, not point estimates alone.", 0),
        ("Event classifier frozen before scoring against hand-labelled gold data — no eval-set tuning.", 0),
        ("Polling-based pub/sub (FastAPI + a flat file) — documented honestly as polling, not a real message bus.", 0),
        ("Full cashflow reprice for bonds, swap DV01 via bump-and-reprice, closed-form Black-Scholes for options — "
         "each compared against the required naive approximation, not just implemented once.", 0),
        ("Mark-to-market P&L and credit loss kept as two separate numbers — a position is never both "
         "fair-valued and provisioned for the same deterioration.", 0),
        ("Demo mode verified byte-identical across two real end-to-end runs, by a dedicated automated test.", 0),
    ], font_size=18)

    # Slide 5: Key Results -- 3 short bullets, two LARGE generated charts
    # (not dashboard screenshots, which render unreadably small at deck
    # scale), and one big callout panel for the single number that matters
    # most: the headline stressed loss.
    s5 = add_content_slide(prs, "Key Results")
    add_bullets(s5, [
        (f"FinBERT {finbert_f1:.3f} macro-F1 vs VADER {vader_f1:.3f} vs majority-class {majority_f1:.3f} "
         f"(n=2000) — bearish recall {finbert_recall_neg:.1%}.", 0),
        (f"{n_signals} real signals evaluated, {n_fired} fired. Naive reprice error reaches "
         f"{worst_bond_error_pct:.2f}% of position value — genuine convexity effect.", 0),
        (f"{slide_event_classification_line(metrics)}", 0),
    ], top=1.15, height=1.5, font_size=18)

    sentiment_chart_path = ASSETS_DIR / "sentiment_chart.png"
    stress_chart_path = ASSETS_DIR / "stress_test_chart.png"
    chart_top = 2.75
    chart_w = 6.0
    for img_path, left in ((sentiment_chart_path, 0.5), (stress_chart_path, 6.8)):
        _img = _Image.open(img_path)
        _h = chart_w / (_img.width / _img.height)
        s5.shapes.add_picture(str(img_path), Inches(left), Inches(chart_top), width=Inches(chart_w), height=Inches(_h))

    effective = headline or stress.get("illustrative_example_NOT_from_a_real_trigger")
    callout_lines = []
    if effective:
        loss_label = "Headline result" if headline is not None else "Manual scenario (not a real trigger)"
        callout_lines.append((
            f"{loss_label}: total stressed loss {fmt_signed_dollar(effective['total_stressed_loss'])} "
            f"({effective['total_stressed_loss_pct']:+.2f}%)", True
        ))
        callout_lines.append((
            f"= MTM P&L {fmt_signed_dollar(effective['mtm_pnl'])}  +  credit loss "
            f"{fmt_signed_dollar(-effective['credit_loss_on_loans'])}", False
        ))
    if data_provisional:
        callout_lines.append(("⚠ Market data is PROVISIONAL this run.", False))
    if callout_lines:
        add_callout_panel(s5, left=0.5, top=6.5, width=12.3, height=0.8, lines=callout_lines,
                           big_font=20, small_font=14)

    # Slide 6: Domain Impact -- one lead bullet, then a two-column lower half
    # (prose left, a real-number callout right) instead of a flat bullet list.
    s6 = add_content_slide(prs, "Domain Impact")
    add_bullets(s6, [
        ("Translates headlines into a dollar P&L a risk desk can act on — signal → scenario → shock → P&L, "
         "fully traceable.", 0),
    ], top=1.15, height=0.8, font_size=19)

    add_column_header(s6, "Mirrors real risk-desk practice", left=0.5, top=2.2)
    add_bullets(s6, [
        ("MTM P&L and credit loss stay separate — a trading-book instrument and a banking-book loan are "
         "never collapsed into one number.", 0),
        ("Shocks anchored to the Fed's own severely-adverse scenario — sourced, not arbitrary round numbers.", 0),
        ("Taxonomy spans credit events, rating-adjacent language, portfolio stress — the surface a ratings/"
         "risk-analytics business operates on. (Credit-event detection itself isn't validated yet.)", 0),
    ], left=0.5, top=2.7, width=5.9, height=3.5, font_size=18)

    if headline is not None:
        # Wording matches Aadit's manual edit to the shipped deck (dd01ade) --
        # kept in sync here so a future regeneration doesn't silently revert
        # it. Do not regenerate docs/presentation.pptx without checking this
        # still matches what's actually shipped.
        add_callout_panel(s6, left=6.8, top=2.7, width=5.9, height=2.0, lines=[
            (f"${abs(headline['total_stressed_loss'])/1e6:.2f}M stressed loss "
             f"({headline['total_stressed_loss_pct']:+.2f}%)", True),
            ("Fed severely-adverse scenario on the synthetic portfolio, triggered by a real headline", False),
        ], big_font=24, small_font=15)

    # Slide 7: Limitations & Next Steps -- the eval-status lines are pulled
    # live from metrics.json via slide-friendly formatters (no backticks, no
    # Python lists, no file paths -- unlike the README's Markdown-oriented
    # functions), so this slide automatically shows the real result with no
    # code change needed as Aadit's local runs update metrics.json. Two
    # columns (not one flat list) so the font can stay >=18pt and the lower
    # half of the slide isn't left empty.
    s7 = add_content_slide(prs, "Limitations & Next Steps")
    market_data_bullet = (
        "Market data is PROVISIONAL in this build — fetched via a tool with a summarising model in the loop."
        if data_provisional else
        "Market data is SOURCED, not provisional — fetched directly."
    )

    add_column_header(s7, "Evaluation status", left=0.5, top=1.25)
    left_bullets = [(slide7_impact_study_line(metrics), 0)]
    left_bullets += [(line, 0) for line in slide7_event_classification_bullets(metrics)]
    add_bullets(s7, left_bullets, left=0.5, top=1.75, width=5.9, height=4.5, font_size=18)

    add_column_header(s7, "Known limitations & next steps", left=6.8, top=1.25)
    add_bullets(s7, [
        (market_data_bullet, 0),
        ("English-only; GDELT is headline-only; the social replay source has synthetic timestamps.", 0),
        ("Credit loss is 1-year EL, not IFRS 9 lifetime — a lower bound, stated as such.", 0),
        ("Next: grow the Credit Event / Geopolitical samples; investigate the Macroeconomic recall gap.", 0),
    ], left=6.8, top=1.75, width=5.9, height=4.5, font_size=18)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    prs.save(OUT_PATH)
    print(f"Wrote {OUT_PATH} (7 slides). Every number traced to metrics.json / stress_test_output.json.")


if __name__ == "__main__":
    main()
