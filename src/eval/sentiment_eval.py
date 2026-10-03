"""Phase 3.1: sentiment evaluation on a dataset FinBERT was NOT fine-tuned on
(zeroshot/twitter-financial-news-sentiment validation split — confirmed disjoint
from Financial PhraseBank, see docs/DATA_VERIFICATION.md).

Methodology discipline (see docs/ASSUMPTIONS.md): nothing is tuned on this split.
The label mapping (Bearish/Bullish/Neutral -> negative/positive/neutral) and the
"predicted label = argmax probability" rule are both fixed before this script is
ever run against it.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np
from sklearn.metrics import accuracy_score, f1_score

from src.ingestion.social_twitter_replay import LABEL_MAP
from src.nlp.sentiment import FinBertSentimentScorer, SentimentScorer, VaderSentimentScorer

N_BOOTSTRAP = 2000
RNG_SEED = 42  # fixed for reproducibility, not tuned for a favourable result


@dataclass
class EvalRow:
    text: str
    gold_label: str  # negative|positive|neutral


def fetch_eval_rows(limit: int = 2000) -> list[EvalRow]:
    import requests

    rows: list[EvalRow] = []
    offset = 0
    page_size = 100
    while len(rows) < limit:
        resp = requests.get(
            "https://datasets-server.huggingface.co/rows",
            params={
                "dataset": "zeroshot/twitter-financial-news-sentiment",
                "config": "default",
                "split": "validation",
                "offset": offset,
                "length": page_size,
            },
            timeout=20,
        )
        resp.raise_for_status()
        payload = resp.json()
        page_rows = payload.get("rows", [])
        if not page_rows:
            break
        for r in page_rows:
            row = r["row"]
            label = LABEL_MAP.get(row["label"])
            if label:
                rows.append(EvalRow(text=row["text"], gold_label=label))
        offset += page_size
        total = payload.get("num_rows_total")
        if total is not None and offset >= total:
            break
    return rows[:limit]


def bootstrap_ci(y_true: list[str], y_pred: list[str], metric_fn, n_bootstrap: int = N_BOOTSTRAP) -> tuple[float, float, float]:
    rng = np.random.default_rng(RNG_SEED)
    n = len(y_true)
    y_true_arr = np.array(y_true)
    y_pred_arr = np.array(y_pred)
    point = metric_fn(y_true_arr, y_pred_arr)
    stats = []
    for _ in range(n_bootstrap):
        idx = rng.integers(0, n, n)
        stats.append(metric_fn(y_true_arr[idx], y_pred_arr[idx]))
    lo, hi = np.percentile(stats, [2.5, 97.5])
    return float(point), float(lo), float(hi)


def evaluate_scorer(scorer: SentimentScorer, rows: list[EvalRow], model_name: str) -> dict:
    y_true, y_pred = [], []
    t0 = time.perf_counter()
    for row in rows:
        result = scorer.score(row.text)
        y_true.append(row.gold_label)
        y_pred.append(result.label)
    elapsed = time.perf_counter() - t0

    acc, acc_lo, acc_hi = bootstrap_ci(y_true, y_pred, accuracy_score)
    f1, f1_lo, f1_hi = bootstrap_ci(
        y_true, y_pred, lambda yt, yp: f1_score(yt, yp, average="macro", zero_division=0)
    )

    return {
        "model": model_name,
        "n_examples": len(rows),
        "accuracy": round(acc, 4),
        "accuracy_ci95": [round(acc_lo, 4), round(acc_hi, 4)],
        "macro_f1": round(f1, 4),
        "macro_f1_ci95": [round(f1_lo, 4), round(f1_hi, 4)],
        "latency_s_total": round(elapsed, 2),
        "latency_ms_per_doc": round(elapsed / max(len(rows), 1) * 1000, 2),
        "throughput_docs_per_s": round(len(rows) / max(elapsed, 1e-9), 2),
    }


def run(limit: int = 2000, include_finbert: bool = True) -> dict:
    rows = fetch_eval_rows(limit=limit)
    results = {"dataset": "zeroshot/twitter-financial-news-sentiment:validation", "n_fetched": len(rows)}

    vader_result = evaluate_scorer(VaderSentimentScorer(), rows, "vader")
    results["vader"] = vader_result

    if include_finbert:
        finbert_result = evaluate_scorer(FinBertSentimentScorer(), rows, "finbert")
        results["finbert"] = finbert_result

    return results
