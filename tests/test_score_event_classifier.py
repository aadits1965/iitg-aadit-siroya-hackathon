"""score_event_classifier.py must refuse to score a gold set that isn't
provably blind-human-labelled (label_source == "human_blind" on every row),
and its macro-F1 must not be dragged down by classes with zero support in
the gold sample -- see docs/ASSUMPTIONS.md for the contamination bug this
fixes."""
import csv
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import score_event_classifier as sec  # noqa: E402


def _write_gold_csv(path: Path, rows: list[dict]):
    fieldnames = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _row(doc_id, text, gold_label, label_source="human_blind"):
    return {
        "doc_id": doc_id, "source": "x", "published_at_utc": "2026-01-01T00:00:00Z",
        "text": text, "suggested_label_do_not_use_as_gold": "Other",
        "gold_label": gold_label, "label_source": label_source,
    }


class TestWilsonCI:
    def test_known_case_matches_closed_form(self):
        # 44/48 -- cross-checked against the entity-linking audit's own
        # reported Wilson 95% CI [80.4%, 96.7%] for the same proportion.
        lo, hi = sec.wilson_ci(44, 48)
        assert lo == pytest.approx(0.804, abs=0.002)
        assert hi == pytest.approx(0.967, abs=0.002)

    def test_zero_n_returns_zero_zero(self):
        assert sec.wilson_ci(0, 0) == (0.0, 0.0)

    def test_perfect_accuracy_interval_still_bounded_below_one(self):
        lo, hi = sec.wilson_ci(10, 10)
        assert hi <= 1.0
        assert lo < 1.0  # a 95% CI from a small perfect sample never claims certainty


class TestMacroAvgOverPresentClasses:
    def test_absent_class_excluded_from_macro_average(self):
        all_classes = ["A", "B", "C"]
        y_true = ["A", "A", "B", "B"]  # C never appears in the gold set
        y_pred = ["A", "A", "B", "B"]  # perfect predictions
        macro_avg, present = sec.macro_avg_over_present_classes(y_true, y_pred, all_classes)
        assert present == ["A", "B"]
        assert macro_avg["f1-score"] == pytest.approx(1.0)  # not dragged down by C's 0 support

    def test_matches_full_report_when_all_classes_present(self):
        all_classes = ["A", "B"]
        y_true = ["A", "B", "A", "B"]
        y_pred = ["A", "A", "A", "B"]
        macro_avg, present = sec.macro_avg_over_present_classes(y_true, y_pred, all_classes)
        assert present == all_classes


class TestRefusalGates:
    def test_refuses_when_label_source_column_missing(self, tmp_path, monkeypatch, capsys):
        gold_path = tmp_path / "gold.csv"
        rows = [{
            "doc_id": "d1", "source": "x", "published_at_utc": "t", "text": "a",
            "suggested_label_do_not_use_as_gold": "Other", "gold_label": "Other",
        }]  # no label_source column at all
        _write_gold_csv(gold_path, rows)
        monkeypatch.setattr(sec, "GOLD_PATH", gold_path)
        monkeypatch.setattr(sec, "METRICS_PATH", tmp_path / "metrics.json")

        with pytest.raises(SystemExit) as exc:
            sec.main()
        assert exc.value.code != 0
        assert "label_source" in capsys.readouterr().out
        assert not (tmp_path / "metrics.json").exists()

    def test_refuses_when_any_row_not_human_blind(self, tmp_path, monkeypatch, capsys):
        gold_path = tmp_path / "gold.csv"
        rows = [
            _row("d1", "text one", "Other", label_source="human_blind"),
            _row("d2", "text two", "Other", label_source=""),  # the exact contamination shape
        ]
        _write_gold_csv(gold_path, rows)
        monkeypatch.setattr(sec, "GOLD_PATH", gold_path)
        monkeypatch.setattr(sec, "METRICS_PATH", tmp_path / "metrics.json")

        with pytest.raises(SystemExit) as exc:
            sec.main()
        assert exc.value.code != 0
        assert "human_blind" in capsys.readouterr().out
        assert not (tmp_path / "metrics.json").exists()

    def test_refuses_when_unlabelled_rows_remain(self, tmp_path, monkeypatch, capsys):
        gold_path = tmp_path / "gold.csv"
        rows = [_row("d1", "text one", "")]
        _write_gold_csv(gold_path, rows)
        monkeypatch.setattr(sec, "GOLD_PATH", gold_path)
        monkeypatch.setattr(sec, "METRICS_PATH", tmp_path / "metrics.json")

        with pytest.raises(SystemExit):
            sec.main()
        assert not (tmp_path / "metrics.json").exists()

    def test_scores_successfully_when_all_rows_human_blind(self, tmp_path, monkeypatch):
        gold_path = tmp_path / "gold.csv"
        rows = [
            _row("d1", "Company announces new product launch", "Product Launch"),
            _row("d2", "Stock market falls on inflation fears", "Macroeconomic"),
            _row("d3", "Random unrelated headline", "Other"),
        ]
        _write_gold_csv(gold_path, rows)
        metrics_path = tmp_path / "metrics.json"
        monkeypatch.setattr(sec, "GOLD_PATH", gold_path)
        monkeypatch.setattr(sec, "METRICS_PATH", metrics_path)

        sec.main()  # must not raise/exit

        import json
        written = json.loads(metrics_path.read_text(encoding="utf-8"))
        result = written["event_classification_eval"]
        assert result["n_gold_examples"] == 3
        assert "majority_baseline" in result
        assert result["majority_baseline"]["description"] == "always predicts 'Other'"
        assert "accuracy_ci95" in result
        assert "accuracy_ci95" in result["majority_baseline"]
        assert "macro_avg_classes_included" in result
