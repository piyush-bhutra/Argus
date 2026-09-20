"""Evidence corpus construction for BM25 retrieval. Pure functions, no download."""
import pytest

from scripts.prepare_fever import build_corpus, evidence_id, normalise_fever_text


# --- FEVER wiki markup ------------------------------------------------------

def test_normalise_expands_bracket_markup():
    assert normalise_fever_text("Jackie -LRB-2016 film-RRB- was a film") == (
        "Jackie (2016 film) was a film"
    )


def test_normalise_expands_remaining_entity_markup():
    assert normalise_fever_text("a -COLON- b") == "a : b"
    assert normalise_fever_text("-LSB-note-RSB-") == "[note]"


def test_normalise_turns_page_title_underscores_into_spaces():
    assert normalise_fever_text("Jackie_-LRB-2016_film-RRB-") == "Jackie (2016 film)"


def test_normalise_collapses_whitespace():
    assert normalise_fever_text("  too   many\n spaces  ") == "too many spaces"


def test_normalise_is_idempotent():
    once = normalise_fever_text("Jackie_-LRB-2016_film-RRB-")
    assert normalise_fever_text(once) == once


def test_normalise_tolerates_empty_and_none():
    assert normalise_fever_text("") == ""
    assert normalise_fever_text(None) == ""


# --- evidence ids -----------------------------------------------------------

def test_evidence_id_is_stable_and_unique_per_sentence():
    assert evidence_id("Jackie_-LRB-2016_film-RRB-", 0) == evidence_id(
        "Jackie_-LRB-2016_film-RRB-", 0
    )
    assert evidence_id("Page", 0) != evidence_id("Page", 1)
    assert evidence_id("Page_A", 0) != evidence_id("Page_B", 0)


def test_evidence_id_accepts_string_sentence_numbers():
    # The dataset stores the sentence index as a string.
    assert evidence_id("Page", "3") == evidence_id("Page", 3)


# --- corpus -----------------------------------------------------------------

def _ev(page, sid, text):
    return [page, sid, text]


def test_build_corpus_extracts_and_normalises():
    corpus, _ = build_corpus({"c1": [_ev("Jackie_-LRB-2016_film-RRB-", "0", "Jackie is a -LRB-film-RRB- .")]})
    assert len(corpus) == 1
    assert corpus[0]["text"] == "Jackie is a (film) ."
    assert corpus[0]["page"] == "Jackie (2016 film)"


def test_build_corpus_dedupes_the_same_sentence_across_claims():
    shared = _ev("Page", "0", "Shared sentence .")
    corpus, _ = build_corpus({"c1": [shared], "c2": [shared], "c3": [_ev("Page", "1", "Other .")]})
    assert len(corpus) == 2


def test_build_corpus_maps_each_claim_to_its_gold_ids():
    corpus, gold = build_corpus({
        "c1": [_ev("P", "0", "one ."), _ev("P", "1", "two .")],
        "c2": [_ev("P", "1", "two .")],
    })
    ids = {row["id"] for row in corpus}
    assert set(gold["c1"]) <= ids
    assert len(gold["c1"]) == 2
    assert gold["c2"] == [evidence_id("P", "1")]


def test_build_corpus_is_deterministic():
    data = {"c1": [_ev("B", "1", "b .")], "c2": [_ev("A", "0", "a .")]}
    assert build_corpus(data)[0] == build_corpus(data)[0]


def test_build_corpus_skips_malformed_and_empty_evidence():
    corpus, gold = build_corpus({
        "ok": [_ev("P", "0", "good .")],
        "short": [["P", "0"]],          # missing the sentence
        "blank": [_ev("P", "2", "   ")],  # whitespace only
        "none": [],
    })
    assert [r["text"] for r in corpus] == ["good ."]
    assert gold["short"] == [] and gold["blank"] == [] and gold["none"] == []


def test_build_corpus_refuses_to_return_an_empty_corpus_silently():
    """An empty corpus would make retrieval return nothing and the symbolic layer
    abstain on everything - a silent, total failure. It must be loud."""
    with pytest.raises(ValueError, match="no usable evidence"):
        build_corpus({"c1": [], "c2": []})
