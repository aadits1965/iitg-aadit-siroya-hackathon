"""AI/NLP Risk Engine dashboard (Phase 5). Five tabs, each reading real files
written by the CLI scripts (results/signals.jsonl, results/metrics.json,
results/stress_test_output.json) -- the dashboard never fabricates or
recomputes a headline number the scripts didn't already produce. Launch via
`python run.py --mode demo` (see that file for what "demo" vs "live" means).
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.dashboard.data import (  # noqa: E402
    load_latest_equity_spot,
    load_metrics,
    load_scenario_config,
    load_signals,
    load_stress_output,
)
from src.dashboard.palette import CATEGORICAL  # noqa: E402
from src.modules.stress_test.curve import MissingCurveCacheError, load_curve  # noqa: E402
from src.modules.stress_test.portfolio import load_portfolio  # noqa: E402
from src.modules.stress_test.revaluation import revalue_portfolio  # noqa: E402
from src.modules.stress_test.shocks import build_shock_set  # noqa: E402
from src.modules.stress_test.trigger import evaluate_signals  # noqa: E402
from src.nlp.event_classification import EVENT_CLASSES  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]

st.set_page_config(page_title="AI/NLP Risk Engine", layout="wide")
st.title("AI/NLP Risk Engine — S&P Global & Crisil Campus Hackathon 2026")
st.caption(
    "Every number on this page is read from a file a script in `scripts/` already wrote "
    "(results/signals.jsonl, results/metrics.json, results/stress_test_output.json) — "
    "nothing here is computed fresh by the dashboard itself, except the Scenario Explorer tab, "
    "which says so explicitly."
)

tab_feed, tab_quality, tab_stress, tab_explorer, tab_audit = st.tabs(
    ["📡 Live Signal Feed", "📊 Engine Quality", "💥 Stress Test", "🔍 Scenario Explorer", "📋 Audit Log"]
)

# ---------------------------------------------------------------------------
# Tab 1: Live Signal Feed
# ---------------------------------------------------------------------------
with tab_feed:
    signals = load_signals()
    if not signals:
        st.warning("No signals found. Run `python scripts/run_engine.py` first (see docs/USER_TODO.md).")
    else:
        st.subheader(f"{len(signals)} signals in results/signals.jsonl")

        col1, col2, col3 = st.columns(3)
        with col1:
            min_impact = st.slider("Minimum impact score", 1.0, 10.0, 1.0, 0.5)
        with col2:
            event_filter = st.multiselect("Event class", EVENT_CLASSES, default=[])
        with col3:
            all_sources = sorted({s for sig in signals for s in sig["sources"]})
            source_filter = st.multiselect("Source", all_sources, default=[])

        rows = []
        for sig in signals:
            if sig["impact"]["score"] < min_impact:
                continue
            if event_filter and sig["event"]["event_class"] not in event_filter:
                continue
            if source_filter and not set(sig["sources"]) & set(source_filter):
                continue
            rows.append({
                "created_at_utc": sig["created_at_utc"],
                "headline": sig["text_preview"][:90],
                "tickers": ", ".join(sig["tickers"]) or "—",
                "sectors": ", ".join(sig.get("sectors", [])) or "—",
                "macro_tags": ", ".join(sig.get("macro_tags", [])) or "—",
                "sentiment": round(sig["sentiment"]["score"], 3),
                "sentiment_label": sig["sentiment"]["label"],
                "event_class": sig["event"]["event_class"],
                "impact_score": sig["impact"]["score"],
                "sources": ", ".join(sig["sources"]),
                "signal_id": sig["signal_id"],
            })

        df = pd.DataFrame(rows).sort_values("impact_score", ascending=False)
        st.caption(f"{len(df)} signals match the current filters")
        st.dataframe(
            df.drop(columns=["signal_id"]),
            use_container_width=True,
            height=420,
            column_config={
                "impact_score": st.column_config.ProgressColumn("Impact", min_value=1, max_value=10, format="%.2f"),
                "sentiment": st.column_config.NumberColumn("Sentiment", format="%.3f"),
            },
        )

        st.markdown("#### Impact-score component breakdown")
        if len(df) > 0:
            selected_id = st.selectbox("Pick a signal to inspect", df["signal_id"], format_func=lambda sid: next(
                r["headline"] for r in rows if r["signal_id"] == sid
            ))
            sig = next(s for s in signals if s["signal_id"] == selected_id)
            comp = sig["impact"]["components"]
            fig = go.Figure(go.Bar(
                x=list(comp.values()), y=list(comp.keys()), orientation="h",
                marker_color=CATEGORICAL[0],
            ))
            fig.update_layout(
                title=f"Impact = {sig['impact']['score']} — {sig['event']['event_class']}",
                xaxis_title="Component value (0-1)", height=280, margin=dict(l=10, r=10, t=40, b=10),
            )
            st.plotly_chart(fig, use_container_width=True)
            st.json(sig, expanded=False)

# ---------------------------------------------------------------------------
# Tab 2: Engine Quality
# ---------------------------------------------------------------------------
with tab_quality:
    metrics = load_metrics()
    st.subheader("Sentiment: FinBERT vs VADER vs majority-class baseline")
    st.caption(
        "Macro-F1 is the headline metric, not accuracy — the eval split is class-imbalanced "
        "(see results below), so a model that always predicts 'neutral' gets high accuracy "
        "while having zero recall on the minority classes."
    )

    sent = metrics.get("sentiment_eval")
    if not sent:
        st.warning("No sentiment_eval block in results/metrics.json. Run `python scripts/run_sentiment_eval.py`.")
    else:
        st.caption(
            f"Dataset: {sent['dataset']} · n={sent['n_fetched']} · "
            f"label distribution: {sent['label_distribution']}"
        )
        model_order = ["majority_baseline", "vader", "finbert"]
        model_labels = {"majority_baseline": "Majority class", "vader": "VADER", "finbert": "FinBERT"}
        present = [m for m in model_order if m in sent]

        fig = go.Figure()
        for i, m in enumerate(present):
            r = sent[m]
            lo, hi = r["macro_f1_ci95"]
            fig.add_trace(go.Bar(
                name=model_labels[m], x=[model_labels[m]], y=[r["macro_f1"]],
                error_y=dict(type="data", array=[hi - r["macro_f1"]], arrayminus=[r["macro_f1"] - lo]),
                marker_color=CATEGORICAL[i], showlegend=False,
            ))
        fig.update_layout(title="Macro-F1 (95% bootstrap CI)", yaxis_title="Macro-F1", height=360,
                           margin=dict(l=10, r=10, t=40, b=10))
        st.plotly_chart(fig, use_container_width=True)

        cols = st.columns(len(present))
        for col, m in zip(cols, present):
            r = sent[m]
            col.metric(model_labels[m], f"{r['macro_f1']:.3f}", help=f"Accuracy {r['accuracy']:.1%}")

        st.markdown("#### FinBERT per-class breakdown (primary model)")
        if "finbert" in sent:
            pc = sent["finbert"]["per_class"]
            st.dataframe(pd.DataFrame(pc).T, use_container_width=True)
            st.caption(
                f"Bearish (negative) recall: {pc['negative']['recall']:.1%} — the metric that matters "
                f"most for a risk engine (missing a real bearish signal is the costlier error)."
            )

    st.divider()
    st.subheader("Event classification")
    gold_path = ROOT / "data" / "eval" / "event_gold.csv"
    if gold_path.exists():
        gold_df = pd.read_csv(gold_path)
        labelled = gold_df["gold_label"].notna().sum() if "gold_label" in gold_df else 0
        total = len(gold_df)
        st.progress(labelled / total if total else 0, text=f"Gold labels: {labelled}/{total} rows labelled")
        if labelled < total:
            st.info("Per-class precision/recall/confusion matrix are pending until labelling is complete "
                    "(see docs/USER_TODO.md) — reporting the rule baseline's own guesses as gold would be circular.")
    else:
        st.warning("No data/eval/event_gold.csv found.")

    st.divider()
    st.subheader("Impact Score event study")
    ies = metrics.get("impact_score_event_study")
    if not ies:
        st.info(
            "Not yet run against a real sample in this environment — GDELT (needed for a large enough "
            "timestamped, ticker-linked sample) is blocked from this dev sandbox. See "
            "docs/EVALUATION.md section 3 and docs/USER_TODO.md for the exact command to run once real "
            "GDELT data is available."
        )
    else:
        c1, c2, c3 = st.columns(3)
        c1.metric("n resolved", ies["n_resolved"])
        c2.metric("Spearman r", f"{ies['spearman_r']:.3f}" if ies["spearman_r"] is not None else "—")
        c3.metric("Power adequate (n≥200)", "Yes" if ies["power_adequate"] else "No")
        if not ies["power_adequate"]:
            st.warning(ies["note"])

# ---------------------------------------------------------------------------
# Tab 3: Stress Test
# ---------------------------------------------------------------------------
with tab_stress:
    out = load_stress_output()
    if not out:
        st.warning("No results/stress_test_output.json found. Run `python scripts/run_stress_test.py`.")
    else:
        if out.get("data_provisional"):
            st.error(
                "⚠️ **Market data is PROVISIONAL** — the yield curve and/or equity prices were fetched "
                "via a tool that passes content through a summarising model, not a direct download. "
                "Run `python scripts/verify_provisional_data.py` before treating these numbers as final. "
                "See docs/DATA_VERIFICATION.md section 9."
            )

        st.caption(f"Curve as-of {out['curve_as_of']} · {out['n_signals_evaluated']} signals evaluated · "
                   f"{out['n_fired']} fired a stress test")

        headline = out.get("headline_scenario")
        if not headline:
            st.warning("**Manual scenario — not triggered by a real signal.** No real signal has fired a "
                       "stress test yet (none exceeded the impact threshold). Showing a manually-constructed "
                       "scenario below instead.")
            headline = out.get("illustrative_example_NOT_from_a_real_trigger")

        if headline:
            is_real = "signal_id" in headline
            st.subheader("✅ Real triggered signal" if is_real
                         else "🔶 Manual scenario — not triggered by a real signal")
            if is_real:
                st.markdown(f"**Headline:** {headline.get('headline_text', '—')}")
                st.caption(f"Signal `{headline['signal_id']}` · impact={headline['impact_score']} · "
                           f"{headline['trigger_reason']}")
            st.markdown(f"**Scenario:** `{headline['tier']}` ({headline['scope']}) — {headline['narrative']}")

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Value before", f"${headline['total_value_before']:,.0f}")
            c2.metric("Value after", f"${headline['total_value_after']:,.0f}",
                      delta=f"{headline['total_stressed_loss']:,.0f}")
            c3.metric("MTM P&L", f"${headline['mtm_pnl']:,.0f}",
                      help="Bonds, swaps, options, FX forwards — fair-valued")
            c4.metric("Credit loss", f"${headline['credit_loss_on_loans']:,.0f}",
                      help="Loans only: Δ(PD × LGD × EAD) — never also fair-valued, see docs/ASSUMPTIONS.md")

            st.markdown("#### P&L by asset class")
            pnl = headline["pnl_by_asset_class"]
            colors = ["#2a78d6" if v >= 0 else "#e34948" for v in pnl.values()]
            fig = go.Figure(go.Bar(x=list(pnl.keys()), y=list(pnl.values()), marker_color=colors))
            fig.update_layout(height=320, margin=dict(l=10, r=10, t=10, b=10), yaxis_title="P&L ($)")
            st.plotly_chart(fig, use_container_width=True)

            cc1, cc2 = st.columns(2)
            with cc1:
                st.markdown("#### P&L by sector")
                pnl_sec = headline["pnl_by_sector"]
                fig2 = go.Figure(go.Bar(
                    x=list(pnl_sec.values()), y=list(pnl_sec.keys()), orientation="h",
                    marker_color=["#2a78d6" if v >= 0 else "#e34948" for v in pnl_sec.values()],
                ))
                fig2.update_layout(height=320, margin=dict(l=10, r=10, t=10, b=10))
                st.plotly_chart(fig2, use_container_width=True)
            with cc2:
                st.markdown("#### Top 10 contributors")
                contrib_df = pd.DataFrame(headline["top_10_contributors"])
                st.dataframe(contrib_df, use_container_width=True, height=320)

        st.divider()
        st.subheader("Naive approximation vs full reprice (required comparison)")
        nf = out.get("naive_vs_full_reprice", {})
        c1, c2 = st.columns(2)
        with c1:
            st.markdown(f"**Bond** `{nf.get('bond', {}).get('position_id', '—')}` — duration-only vs full cashflow reprice")
            bond_df = pd.DataFrame(nf.get("bond", {}).get("comparisons", []))
            if not bond_df.empty:
                fig = go.Figure()
                fig.add_trace(go.Scatter(x=bond_df["shock"], y=bond_df["full_reprice"], name="Full reprice",
                                          mode="lines+markers", line=dict(color="#2a78d6")))
                fig.add_trace(go.Scatter(x=bond_df["shock"], y=bond_df["naive_duration_only"], name="Duration-only",
                                          mode="lines+markers", line=dict(color="#eb6834", dash="dash")))
                fig.update_layout(height=320, margin=dict(l=10, r=10, t=10, b=10), yaxis_title="Price")
                st.plotly_chart(fig, use_container_width=True)
                st.dataframe(bond_df, use_container_width=True)
        with c2:
            st.markdown(f"**Option** `{nf.get('option', {}).get('position_id', '—')}` — delta-only vs full Black-Scholes reprice")
            opt_df = pd.DataFrame(nf.get("option", {}).get("comparisons", []))
            if not opt_df.empty:
                fig = go.Figure()
                fig.add_trace(go.Scatter(x=opt_df["shock"], y=opt_df["full_reprice"], name="Full reprice",
                                          mode="lines+markers", line=dict(color="#2a78d6")))
                fig.add_trace(go.Scatter(x=opt_df["shock"], y=opt_df["naive_delta_only"], name="Delta-only",
                                          mode="lines+markers", line=dict(color="#eb6834", dash="dash")))
                fig.update_layout(height=320, margin=dict(l=10, r=10, t=10, b=10), yaxis_title="Price")
                st.plotly_chart(fig, use_container_width=True)
                st.dataframe(opt_df, use_container_width=True)
        st.caption("Error grows with shock size in both cases — genuine convexity/gamma effect, "
                   "confirmed by tests/test_naive_approx.py.")

        st.divider()
        with st.expander("All fired scenarios (up to 5 highest-impact)"):
            st.json(out.get("fired_scenarios", []), expanded=False)

# ---------------------------------------------------------------------------
# Tab 4: Scenario Explorer (the one tab that computes live, not from a file)
# ---------------------------------------------------------------------------
with tab_explorer:
    st.warning("🔶 **Manual scenario — not triggered by a real signal.** This tab computes a fresh "
               "revaluation live (unlike every other tab, which only reads files already written by a "
               "script) — useful for live Q&A ('what if this were a Credit Event on the Energy sector "
               "instead?'), but every result shown here is a manually-chosen what-if, never a real trigger.")

    try:
        curve = load_curve()
        if curve.is_provisional:
            st.warning("Curve data is PROVISIONAL — see docs/DATA_VERIFICATION.md section 9.")
        portfolio = load_portfolio()
        equity_spot = load_latest_equity_spot()

        c1, c2, c3 = st.columns(3)
        with c1:
            chosen_class = st.selectbox("Event class", EVENT_CLASSES, index=1)
        with c2:
            sectors_available = sorted({p.sector for p in portfolio})
            chosen_sectors = st.multiselect("Affected sector(s) (for entity-specific scopes)", sectors_available)
        with c3:
            chosen_countries = st.multiselect("Affected countr(y/ies)", sorted({p.country for p in portfolio}))

        if st.button("Run scenario", type="primary"):
            shock = build_shock_set(chosen_class, sectors=chosen_sectors, countries=chosen_countries)
            result = revalue_portfolio(portfolio, curve, equity_spot, shock)

            st.markdown("**🔶 Manual scenario — not triggered by a real signal**")
            st.markdown(f"**Scenario:** `{shock.tier_name}` ({shock.scope}) — {shock.narrative}")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Value before", f"${result.total_value_before:,.0f}")
            c2.metric("Value after", f"${result.total_value_after:,.0f}", delta=f"{result.total_stressed_loss:,.0f}")
            c3.metric("MTM P&L", f"${result.mtm_pnl:,.0f}")
            c4.metric("Credit loss", f"${result.credit_loss:,.0f}")

            pnl = result.pnl_by_asset_class()
            fig = go.Figure(go.Bar(x=list(pnl.keys()), y=list(pnl.values()),
                                    marker_color=["#2a78d6" if v >= 0 else "#e34948" for v in pnl.values()]))
            fig.update_layout(height=300, margin=dict(l=10, r=10, t=10, b=10), yaxis_title="P&L ($)")
            st.plotly_chart(fig, use_container_width=True)
            st.dataframe(pd.DataFrame(result.top_contributors(10), columns=["position_id", "pnl"]),
                         use_container_width=True)
    except MissingCurveCacheError as e:
        st.error(str(e))

# ---------------------------------------------------------------------------
# Tab 5: Audit Log
# ---------------------------------------------------------------------------
with tab_audit:
    signals = load_signals()
    cfg = load_scenario_config()
    st.caption(f"Shock config version: `{cfg.get('config_version', 'unknown')}` "
               f"(config/scenarios.yaml) · {len(signals)} signals in log")

    if signals:
        decisions = evaluate_signals(signals)
        rows = []
        for d in decisions:
            rows.append({
                "created_at_utc": d.created_at_utc.isoformat(),
                "signal_id": d.signal_id,
                "event_class": d.event_class,
                "impact_score": d.impact_score,
                "tickers": ", ".join(d.tickers) or "—",
                "fired": "🔴 FIRED" if d.fired else "—",
                "reason": d.reason,
            })
        audit_df = pd.DataFrame(rows).sort_values("created_at_utc", ascending=False)
        fired_only = st.checkbox("Show fired triggers only", value=False)
        if fired_only:
            audit_df = audit_df[audit_df["fired"] != "—"]
        st.dataframe(audit_df, use_container_width=True, height=500)
        st.caption(f"{(audit_df['fired'] != '—').sum() if not fired_only else len(audit_df)} fired / "
                   f"{len(decisions)} total evaluated")
    else:
        st.warning("No signals to audit.")

st.sidebar.markdown("### About")
st.sidebar.caption(
    "AI/NLP Risk Engine prototype — S&P Global & Crisil Campus Hackathon 2026.\n\n"
    "Run with `python run.py --mode demo` (offline, deterministic) or `--mode live` "
    "(pulls fresh data; needs a normal network — see docs/USER_TODO.md)."
)
st.sidebar.caption(f"Page rendered: {datetime.now().isoformat(timespec='seconds')}")
