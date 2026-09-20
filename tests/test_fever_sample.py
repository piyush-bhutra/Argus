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
        assert set(row) == {"claim", "label", "evidence_ids"}
        assert isinstance(row["claim"], str) and row["claim"].strip()
        assert isinstance(row["label"], bool)
        # Gold evidence ids exist to MEASURE retrieval (recall@k). They are never
        # handed to the retriever, which would be oracle retrieval.
        assert isinstance(row["evidence_ids"], list)
        assert all(isinstance(e, str) and e for e in row["evidence_ids"])


def test_sample_gold_evidence_resolves_against_the_corpus():
    """Every gold id must exist in the corpus, or recall@k silently measures
    against ids that can never be retrieved and always reports 0."""
    corpus_file = SAMPLE.parent / "evidence_corpus.json"
    if not (SAMPLE.exists() and corpus_file.exists()):
        pytest.skip("sample or corpus not generated (run scripts/prepare_fever.py)")

    rows = json.loads(SAMPLE.read_text(encoding="utf-8"))
    corpus_ids = {r["id"] for r in json.loads(corpus_file.read_text(encoding="utf-8"))}
    dangling = {e for row in rows for e in row["evidence_ids"] if e not in corpus_ids}
    assert not dangling, f"{len(dangling)} gold evidence ids are not in the corpus"


def test_fever_sample_is_class_balanced():
    if not SAMPLE.exists():
        pytest.skip("data/fever_sample.json not generated (run scripts/prepare_fever.py)")

    rows = json.loads(SAMPLE.read_text(encoding="utf-8"))
    n_true = sum(1 for r in rows if r["label"])
    assert n_true == len(rows) - n_true, f"sample is {n_true}T/{len(rows) - n_true}F"
    assert len({r["claim"] for r in rows}) == len(rows), "duplicate claims in sample"
