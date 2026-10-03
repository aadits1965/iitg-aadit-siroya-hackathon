"""Phase 3.1: sentiment evaluation on a dataset FinBERT was NOT fine-tuned on
(zeroshot/twitter-financial-news-sentiment validation split — confirmed disjoint
from Financial PhraseBank, see docs/DATA_VERIFICATION.md).

Methodology discipline (see docs/ASSUMPTIONS.md): nothing is tuned on this split.
The label mapping (Bearish/Bullish/Neutral -> negative/positive/neutral) and the
"predicted label = argmax probability" rule are both fixed before this script is
ever run against it. The one exception, by convention not by violation: the
majority-class baseline is allowed to read the label distribution, since it has
no parameters to fit or search over -- it is the standard "what's the floor"
reference point, not a tuned model.

Macro-F1, not accuracy, is the headline metric: this dataset is class-imbalanced
(see label_distribution below) and accuracy alone rewards a model for doing well
on the majority class while hiding poor minority-class recall.
"""
from __future__ import annotations

import time
from collections import Counter
from dataclasses import dataclass

import numpy as np
from sklearn.metrics import accuracy_score, f1_score, precision_recall_fscore_support

from src.ingestion.social_twitter_replay import LABEL_MAP
from src.nlp.sentiment import FinBertSentimentScorer, SentimentScorer, VaderSentimentScorer

N_BOOTSTRAP = 2000
RNG_SEED = 42  # fixed for reproducibility, not tuned for a favourable result
CLASS_LABELS = ["negative", "positive", "neutral"]


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


def per_class_breakdown(y_true: list[str], y_pred: list[str]) -> dict:
    precision, recall, f1, support = precision_recall_fscore_support(
        y_true, y_pred, labels=CLASS_LABELS, zero_division=0
    )
    return {
        label: {
            "precision": round(float(precision[i]), 4),
            "recall": round(float(recall[i]), 4),
            "f1": round(float(f1[i]), 4),
            "support": int(support[i]),
        }
        for i, label in enumerate(CLASS_LABELS)
    }


def evaluate_predictions(y_true: list[str], y_pred: list[str], model_name: str, elapsed: float, n_examples: int) -> dict:
    acc, acc_lo, acc_hi = bootstrap_ci(y_true, y_pred, accuracy_score)
    f1, f1_lo, f1_hi = bootstrap_ci(
        y_true, y_pred, lambda yt, yp: f1_score(yt, yp, average="macro", zero_division=0)
    )

    return {
        "model": model_name,
        "n_examples": n_examples,
        "macro_f1": round(f1, 4),
        "macro_f1_ci95": [round(f1_lo, 4), round(f1_hi, 4)],
        "accuracy": round(acc, 4),
        "accuracy_ci95": [round(acc_lo, 4), round(acc_hi, 4)],
        "per_class": per_class_breakdown(y_true, y_pred),
        "latency_s_total": round(elapsed, 2),
        "latency_ms_per_doc": round(elapsed / max(n_examples, 1) * 1000, 2),
        "throughput_docs_per_s": round(n_examples / max(elapsed, 1e-9), 2),
    }


def evaluate_scorer(scorer: SentimentScorer, rows: list[EvalRow], model_name: str) -> dict:
    y_true, y_pred = [], []
    t0 = time.perf_counter()
    for row in rows:
        result = scorer.score(row.text)
        y_true.append(row.gold_label)
        y_pred.append(result.label)
    elapsed = time.perf_counter() - t0
    return evaluate_predictions(y_true, y_pred, model_name, elapsed, len(rows))


def evaluate_majority_baseline(rows: list[EvalRow]) -> dict:
    """Floor reference: predict the single most common gold label every time.
    Allowed to read the label distribution (see module docstring) -- it has no
    parameters to fit, so this isn't the kind of tuning the no-tuning-on-eval
    rule is about."""
    y_true = [r.gold_label for r in rows]
    majority_label = Counter(y_true).most_common(1)[0][0]
    y_pred = [majority_label] * len(rows)
    t0 = time.perf_counter()
    elapsed = time.perf_counter() - t0
    result = evaluate_predictions(y_true, y_pred, "majority_class", elapsed, len(rows))
    result["majority_label"] = majority_label
    return result


def run(limit: int = 2000, include_finbert: bool = True) -> dict:
    rows = fetch_eval_rows(limit=limit)
    label_distribution = dict(Counter(r.gold_label for r in rows))

    results = {
        "dataset": "zeroshot/twitter-financial-news-sentiment:validation",
        "n_fetched": len(rows),
        "label_distribution": label_distribution,
    }

    results["majority_baseline"] = evaluate_majority_baseline(rows)
    results["vader"] = evaluate_scorer(VaderSentimentScorer(), rows, "vader")

    if include_finbert:
        results["finbert"] = evaluate_scorer(FinBertSentimentScorer(), rows, "finbert")

    return results
