"""data/fever_sample.json is generated offline (scripts/prepare_fever.py), so
this only checks the shape when the file happens to be there."""
import json
from pathlib import Path

import pytest

SAMPLE = Path(__file__).resolve().parents[1] / "data" / "fever_sample.json"


def test_fever_sample_shape():
    if not SAMPLE.exists():
        pytest.skip("data/fever_sample.json not generated (run scripts/prepare_fever.py)")

    rows = json.loads(SAMPLE.read_text(encoding="utf-8"))
    assert isinstance(rows, list) and rows
    for row in rows:
        assert set(row) == {"claim", "label"}
        assert isinstance(row["claim"], str) and row["claim"].strip()
        assert isinstance(row["label"], bool)


def test_fever_sample_is_class_balanced():
    if not SAMPLE.exists():
        pytest.skip("data/fever_sample.json not generated (run scripts/prepare_fever.py)")

    rows = json.loads(SAMPLE.read_text(encoding="utf-8"))
    n_true = sum(1 for r in rows if r["label"])
    assert n_true == len(rows) - n_true, f"sample is {n_true}T/{len(rows) - n_true}F"
    assert len({r["claim"] for r in rows}) == len(rows), "duplicate claims in sample"
