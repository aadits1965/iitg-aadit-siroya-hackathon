"""The 's' shortcut (accept the rule's suggestion directly into gold_label,
with no record of which rows took it) contaminated the human gold set with
the classifier's own predictions on an unknown subset of rows -- see
docs/ASSUMPTIONS.md. These tests cover the fix: no suggestion shown, no
shortcut offered, every entered label stamped label_source="human_blind",
and --fresh discarding a contaminated prior run."""
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from label_events import (  # noqa: E402
    HUMAN_BLIND,
    build_arg_parser,
    ensure_label_source_column,
    main,
)

FIELDNAMES = ["doc_id", "source", "published_at_utc", "text", "suggested_label_do_not_use_as_gold", "gold_label"]


def _write_csv(path: Path, rows: list[dict], fieldnames=None):
    fieldnames = fieldnames or FIELDNAMES
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _read_csv(path: Path) -> list[dict]:
    with path.open("r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


class TestEnsureLabelSourceColumn:
    def test_adds_missing_column_with_empty_default(self):
        rows = [{"a": "1"}, {"a": "2"}]
        fieldnames = ensure_label_source_column(rows, ["a"])
        assert fieldnames == ["a", "label_source"]
        assert all(r["label_source"] == "" for r in rows)

    def test_leaves_existing_column_untouched(self):
        rows = [{"a": "1", "label_source": "human_blind"}]
        fieldnames = ensure_label_source_column(rows, ["a", "label_source"])
        assert fieldnames == ["a", "label_source"]
        assert rows[0]["label_source"] == "human_blind"


class TestNoSuggestionShortcut:
    def test_s_is_not_a_valid_choice(self, tmp_path, monkeypatch, capsys):
        """The removed 's' shortcut must be rejected like any other invalid
        input, then a real class number must still work."""
        path = tmp_path / "gold.csv"
        _write_csv(path, [
            {"doc_id": "d1", "source": "x", "published_at_utc": "t", "text": "hello",
             "suggested_label_do_not_use_as_gold": "Other", "gold_label": ""},
        ])
        inputs = iter(["s", "6", "q"])
        monkeypatch.setattr("builtins.input", lambda _: next(inputs))
        main(argv=[], path=path)

        out = capsys.readouterr().out
        assert "suggests" not in out.lower()  # the rule suggestion must never be printed
        assert "Invalid input." in out  # 's' was rejected

        rows = _read_csv(path)
        assert rows[0]["gold_label"] == "Other"
        assert rows[0]["label_source"] == HUMAN_BLIND


class TestLabelSourceStamping:
    def test_every_entered_label_is_stamped_human_blind(self, tmp_path, monkeypatch):
        path = tmp_path / "gold.csv"
        _write_csv(path, [
            {"doc_id": "d1", "source": "x", "published_at_utc": "t", "text": "a",
             "suggested_label_do_not_use_as_gold": "Other", "gold_label": ""},
            {"doc_id": "d2", "source": "x", "published_at_utc": "t", "text": "b",
             "suggested_label_do_not_use_as_gold": "Other", "gold_label": ""},
        ])
        inputs = iter(["1", "2"])
        monkeypatch.setattr("builtins.input", lambda _: next(inputs))
        main(argv=[], path=path)

        rows = _read_csv(path)
        assert rows[0]["gold_label"] == "Geopolitical"
        assert rows[1]["gold_label"] == "Macroeconomic"
        assert all(r["label_source"] == HUMAN_BLIND for r in rows)

    def test_quitting_mid_way_leaves_label_source_blank_for_unlabelled_rows(self, tmp_path, monkeypatch):
        path = tmp_path / "gold.csv"
        _write_csv(path, [
            {"doc_id": "d1", "source": "x", "published_at_utc": "t", "text": "a",
             "suggested_label_do_not_use_as_gold": "Other", "gold_label": ""},
            {"doc_id": "d2", "source": "x", "published_at_utc": "t", "text": "b",
             "suggested_label_do_not_use_as_gold": "Other", "gold_label": ""},
        ])
        inputs = iter(["q"])
        monkeypatch.setattr("builtins.input", lambda _: next(inputs))
        main(argv=[], path=path)

        rows = _read_csv(path)
        assert rows[0]["gold_label"] == "" and rows[0]["label_source"] == ""
        assert rows[1]["gold_label"] == "" and rows[1]["label_source"] == ""


class TestFreshFlag:
    def test_fresh_discards_a_contaminated_prior_run(self, tmp_path, monkeypatch):
        path = tmp_path / "gold.csv"
        _write_csv(path, [
            {"doc_id": "d1", "source": "x", "published_at_utc": "t", "text": "a",
             "suggested_label_do_not_use_as_gold": "Other", "gold_label": "Other", "label_source": ""},
        ], fieldnames=FIELDNAMES + ["label_source"])
        inputs = iter(["6"])
        monkeypatch.setattr("builtins.input", lambda _: next(inputs))
        main(argv=["--fresh"], path=path)

        rows = _read_csv(path)
        assert rows[0]["gold_label"] == "Other"
        assert rows[0]["label_source"] == HUMAN_BLIND

    def test_build_arg_parser_has_fresh_flag(self):
        args = build_arg_parser().parse_args(["--fresh"])
        assert args.fresh is True
        args = build_arg_parser().parse_args([])
        assert args.fresh is False
