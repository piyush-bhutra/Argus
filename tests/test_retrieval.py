"""BM25 retrieval over the evidence corpus. Pure, offline, no LLM."""
import pytest

from app.services.retrieval import Retriever, tokenise


CORPUS = [
    {"id": "e1", "page": "Pink Floyd", "sent_id": "0",
     "text": "Pink Floyd were an English rock band formed in London ."},
    {"id": "e2", "page": "Jackie (2016 film)", "sent_id": "0",
     "text": "Jackie is a 2016 biographical drama film directed by Pablo Larrain ."},
    {"id": "e3", "page": "Chrysler Building", "sent_id": "0",
     "text": "The Chrysler Building is a skyscraper in New York City ."},
    {"id": "e4", "page": "Chrysler Building", "sent_id": "1",
     "text": "It was the world 's tallest building for eleven months ."},
]


@pytest.fixture
def retriever():
    return Retriever(CORPUS)


# --- tokenisation -----------------------------------------------------------

def test_tokenise_lowercases_and_drops_punctuation():
    assert tokenise("The Chrysler Building, in N.Y.C.!") == [
        "the", "chrysler", "building", "in", "n", "y", "c"
    ]


def test_tokenise_keeps_digits():
    assert tokenise("formed in 1965") == ["formed", "in", "1965"]


def test_tokenise_handles_empty():
    assert tokenise("") == []
    assert tokenise(None) == []


# --- retrieval --------------------------------------------------------------

def test_retrieve_finds_the_obviously_matching_sentence(retriever):
    hits = retriever.retrieve("Pink Floyd were a rock band from London", k=1)
    assert [h["id"] for h in hits] == ["e1"]


def test_retrieve_returns_at_most_k(retriever):
    q = "Chrysler Building skyscraper New York tallest"
    assert len(retriever.retrieve(q, k=2)) == 2
    assert len(retriever.retrieve(q, k=10)) <= len(CORPUS)


def test_terms_in_over_half_the_corpus_score_zero():
    """Okapi IDF goes to zero (and below) once a term appears in more than half
    the documents, so a query made only of such terms retrieves nothing. Harmless
    on the real 3.5k-sentence corpus where content words are rare, but it bites in
    tiny corpora - documented here so the behaviour is not rediscovered as a bug."""
    r = Retriever(CORPUS)
    assert r.retrieve("building", k=2) == []    # in 2 of 4 docs -> idf 0
    assert r.retrieve("chrysler", k=2) != []    # in 1 of 4 docs -> idf positive



def test_retrieve_orders_by_descending_score(retriever):
    hits = retriever.retrieve("Chrysler Building skyscraper", k=4)
    scores = [h["score"] for h in hits]
    assert scores == sorted(scores, reverse=True)


def test_retrieve_carries_corpus_fields_through(retriever):
    hit = retriever.retrieve("Pink Floyd rock band", k=1)[0]
    assert hit["page"] == "Pink Floyd"
    assert hit["text"].startswith("Pink Floyd")
    assert "score" in hit


def test_retrieve_drops_zero_score_hits(retriever):
    """A query sharing no terms with the corpus must return nothing, not the
    arbitrary first k documents - otherwise the fact-checker reasons over
    evidence that has no relation to the argument."""
    assert retriever.retrieve("zzzz qqqq xxxx", k=4) == []


def test_retrieve_on_empty_query_returns_nothing(retriever):
    assert retriever.retrieve("", k=4) == []


def test_retriever_rejects_an_empty_corpus():
    with pytest.raises(ValueError, match="empty corpus"):
        Retriever([])


# --- recall@k ---------------------------------------------------------------

def test_recall_at_k_is_one_when_gold_is_top_hit(retriever):
    assert retriever.recall_at_k("Pink Floyd rock band London", ["e1"], k=1) == 1.0


def test_recall_at_k_is_fractional_on_partial_hits(retriever):
    # Only one of the two Chrysler sentences is reachable from these terms.
    r = retriever.recall_at_k("Chrysler Building skyscraper New York", ["e3", "e4"], k=1)
    assert r == 0.5


def test_recall_at_k_is_none_without_gold(retriever):
    assert retriever.recall_at_k("anything", [], k=5) is None
