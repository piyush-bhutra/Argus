"""Fact-checker: retrieve -> LLM extracts triples -> symbolic rules judge.

The LLM is mocked throughout. What is under test is the orchestration and the
guarantee that the model never decides the verdict.
"""
import json

import pytest

from app.models.schemas import Argument
from app.services import fact_checker
from app.services.retrieval import Retriever


# Okapi IDF is <= 0 for any term appearing in more than half the corpus, so a
# two-document fixture retrieves nothing at all and every test would abstain for
# the wrong reason. The distractors below keep document frequencies realistic.
CORPUS = [
    {"id": "e1", "page": "Jackie (2016 film)", "sent_id": "0",
     "text": "Jackie is a 2016 biographical drama film directed by Pablo Larrain ."},
    {"id": "e2", "page": "Peter Jackson", "sent_id": "0",
     "text": "Peter Jackson is a New Zealand film director ."},
    {"id": "e3", "page": "Pink Floyd", "sent_id": "0",
     "text": "Pink Floyd were an English rock band formed in London ."},
    {"id": "e4", "page": "Chrysler Building", "sent_id": "0",
     "text": "The Chrysler Building is a skyscraper in New York City ."},
    {"id": "e5", "page": "Mount Everest", "sent_id": "0",
     "text": "Mount Everest is the highest mountain above sea level ."},
    {"id": "e6", "page": "Insulin", "sent_id": "0",
     "text": "Insulin is a peptide hormone produced by the pancreas ."},
    {"id": "e7", "page": "Berlin Wall", "sent_id": "0",
     "text": "The Berlin Wall fell on 9 November 1989 ."},
    {"id": "e8", "page": "Columbia River", "sent_id": "0",
     "text": "The Columbia River flows into the Pacific Ocean ."},
]


def _args(*texts):
    return [
        Argument(id=f"arg_{i}", agent="advocate" if i % 2 else "skeptic", round=1,
                 text=t, attacks=[], self_confidence=0.8)
        for i, t in enumerate(texts, 1)
    ]


def _extraction(mapping):
    """Build the JSON the LLM is expected to return: id -> list of triples."""
    return json.dumps({
        "triples": [
            {"source_id": sid, "subject": s, "predicate": p, "object": o, "negated": neg}
            for sid, trips in mapping.items()
            for (s, p, o, neg) in trips
        ]
    })


@pytest.fixture
def retriever():
    return Retriever(CORPUS)


# --- happy paths ------------------------------------------------------------

def test_supported_argument_scores_positive(monkeypatch, retriever):
    monkeypatch.setattr(fact_checker, "call_grok", lambda *a, **k: _extraction({
        "arg_1": [("Jackie", "directed_by", "Pablo Larrain", False)],
        "e1": [("Jackie", "directed_by", "Pablo Larrain", False)],
    }))
    [r] = fact_checker.check_transcript(
        "Jackie was directed by Pablo Larrain.",
        _args("Jackie was directed by Pablo Larrain."),
        retriever=retriever,
    )
    assert r.support_score == 1.0
    assert r.method == "symbolic"
    assert r.rules_fired == ["entailment"]
    assert "e1" in r.evidence_ids


def test_contradicted_argument_scores_negative(monkeypatch, retriever):
    monkeypatch.setattr(fact_checker, "call_grok", lambda *a, **k: _extraction({
        "arg_1": [("Jackie", "directed_by", "Peter Jackson", False)],
        "e1": [("Jackie", "directed_by", "Pablo Larrain", False)],
    }))
    [r] = fact_checker.check_transcript(
        "Jackie was directed by Peter Jackson.",
        _args("Jackie was directed by Peter Jackson."),
        retriever=retriever,
    )
    assert r.support_score == -1.0
    assert r.rules_fired == ["functional_contradiction"]


def test_undecidable_argument_abstains(monkeypatch, retriever):
    """No matching evidence triple -> 0.0 and method 'none'. It must NOT fall
    back to asking the model for a verdict; that is the thing being removed."""
    monkeypatch.setattr(fact_checker, "call_grok", lambda *a, **k: _extraction({
        "arg_1": [("Some Film", "directed_by", "Nobody", False)],
        "e1": [("Jackie", "directed_by", "Pablo Larrain", False)],
    }))
    [r] = fact_checker.check_transcript("x", _args("Some Film was directed by Nobody."),
                                        retriever=retriever)
    assert r.support_score == 0.0
    assert r.method == "none"


def test_scores_average_over_multiple_triples(monkeypatch, retriever):
    monkeypatch.setattr(fact_checker, "call_grok", lambda *a, **k: _extraction({
        "arg_1": [("Jackie", "directed_by", "Pablo Larrain", False),
                  ("Jackie", "directed_by", "Peter Jackson", False)],
        "e1": [("Jackie", "directed_by", "Pablo Larrain", False)],
    }))
    # The text must actually retrieve e1, or there is no KB and it abstains.
    [r] = fact_checker.check_transcript(
        "Jackie Pablo Larrain",
        _args("Jackie was directed by Pablo Larrain and by Peter Jackson."),
        retriever=retriever,
    )
    # one entailment (+1), one functional contradiction (-1)
    assert r.support_score == 0.0
    assert set(r.rules_fired) == {"entailment", "functional_contradiction"}
    assert r.method == "symbolic"   # decided, even though it averages to zero


# --- the model must not judge ----------------------------------------------

def test_one_llm_call_per_transcript(monkeypatch, retriever):
    calls = []

    def fake(prompt, system):
        calls.append(prompt)
        return _extraction({})

    monkeypatch.setattr(fact_checker, "call_grok", fake)
    fact_checker.check_transcript("x", _args("a", "b", "c"), retriever=retriever)
    assert len(calls) == 1


def test_prompt_asks_for_extraction_not_judgement(monkeypatch, retriever):
    seen = {}

    def fake(prompt, system):
        seen["prompt"], seen["system"] = prompt.lower(), system.lower()
        return _extraction({})

    monkeypatch.setattr(fact_checker, "call_grok", fake)
    fact_checker.check_transcript("x", _args("a"), retriever=retriever)
    blob = seen["prompt"] + seen["system"]
    assert "triple" in blob or "subject" in blob
    # The model is a parser here. Asking it to rate truth would reintroduce the
    # exact circularity this redesign removes.
    for forbidden in ("support_score", "how likely", "is this true", "well supported"):
        assert forbidden not in blob


# --- degradation ------------------------------------------------------------

def test_unparseable_llm_response_degrades_to_neutral(monkeypatch, retriever):
    monkeypatch.setattr(fact_checker, "call_grok", lambda *a, **k: "not json at all")
    results = fact_checker.check_transcript("x", _args("a", "b"), retriever=retriever)
    assert [r.support_score for r in results] == [0.0, 0.0]
    assert all(r.method == "none" for r in results)


def test_llm_failure_degrades_to_neutral(monkeypatch, retriever):
    def boom(*a, **k):
        raise RuntimeError("provider down")

    monkeypatch.setattr(fact_checker, "call_grok", boom)
    results = fact_checker.check_transcript("x", _args("a"), retriever=retriever)
    assert results[0].support_score == 0.0


def test_missing_corpus_abstains_without_calling_the_model(monkeypatch):
    """No corpus -> nothing to reason over. It must abstain rather than quietly
    falling back to letting the model decide.

    load_retriever is patched, not just left as None: a bare retriever=None falls
    through to the real corpus on disk, and the resulting call would be swallowed
    by the module's except-Exception, passing this test for the wrong reason.
    """
    called = []
    monkeypatch.setattr(fact_checker, "load_retriever", lambda *a, **k: None)
    monkeypatch.setattr(fact_checker, "call_grok", lambda *a, **k: called.append(1) or "{}")

    results = fact_checker.check_transcript("x", _args("a"), retriever=None)
    assert called == [], "the LLM must not be called when there is no corpus"
    assert [r.support_score for r in results] == [0.0]
    assert results[0].method == "none"


def test_every_argument_gets_exactly_one_result(monkeypatch, retriever):
    monkeypatch.setattr(fact_checker, "call_grok", lambda *a, **k: _extraction({}))
    args = _args("a", "b", "c", "d")
    results = fact_checker.check_transcript("x", args, retriever=retriever)
    assert [r.argument_id for r in results] == [a.id for a in args]


def test_empty_transcript_makes_no_call(monkeypatch, retriever):
    # Counted rather than raised: an AssertionError here would be swallowed by
    # the module's except-Exception and the test would pass regardless.
    called = []
    monkeypatch.setattr(fact_checker, "call_grok", lambda *a, **k: called.append(1) or "{}")
    assert fact_checker.check_transcript("x", [], retriever=retriever) == []
    assert called == []


# --- coverage metric --------------------------------------------------------

def test_coverage_reports_the_decided_fraction():
    from app.models.schemas import FactCheckResult

    results = [
        FactCheckResult(argument_id="a", evidence_sentences=[], support_score=1.0, method="symbolic"),
        FactCheckResult(argument_id="b", evidence_sentences=[], support_score=0.0, method="none"),
        FactCheckResult(argument_id="c", evidence_sentences=[], support_score=-1.0, method="symbolic"),
    ]
    assert fact_checker.symbolic_coverage(results) == pytest.approx(2 / 3)
    assert fact_checker.symbolic_coverage([]) is None
