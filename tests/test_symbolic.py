"""PRD M4 - forward-chaining contradiction detection. Pure logic, no LLM."""
import pytest

from app.services.symbolic import (
    CONTRADICT,
    SUPPORT,
    Triple,
    derive_closure,
    normalise_entity,
    score_triple,
)


def t(s, p, o, negated=False, source="e1"):
    return Triple(subject=s, predicate=p, object=o, negated=negated, source=source)


# --- normalisation ----------------------------------------------------------

def test_normalise_lowercases_and_strips_articles():
    assert normalise_entity("The Chrysler Building") == "chrysler building"
    assert normalise_entity("a film") == "film"


def test_normalise_strips_punctuation_and_whitespace():
    assert normalise_entity("  Pink Floyd, .  ") == "pink floyd"


def test_normalise_is_idempotent():
    once = normalise_entity("The Eiffel Tower.")
    assert normalise_entity(once) == once


def test_normalise_handles_empty():
    assert normalise_entity("") == ""
    assert normalise_entity(None) == ""


# --- forward chaining -------------------------------------------------------

def test_closure_derives_inverse_predicates():
    """(film, directed_by, person) entails (person, directed, film) - a fact not
    literally present in the evidence. This is the forward-chaining step."""
    kb = derive_closure([t("Jackie", "directed_by", "Pablo Larrain")])
    assert any(
        x.subject == "pablo larrain" and x.predicate == "directed" and x.object == "jackie"
        for x in kb
    )


def test_closure_derives_symmetric_predicates_both_ways():
    kb = derive_closure([t("Alice", "married_to", "Bob")])
    pairs = {(x.subject, x.object) for x in kb if x.predicate == "married_to"}
    assert ("alice", "bob") in pairs and ("bob", "alice") in pairs


def test_closure_reaches_a_fixpoint_and_terminates():
    # Symmetric rules could loop forever if the closure did not dedupe.
    kb = derive_closure([t("Alice", "married_to", "Bob"), t("Bob", "married_to", "Alice")])
    assert len({(x.subject, x.predicate, x.object, x.negated) for x in kb}) == len(kb)


def test_closure_preserves_the_original_facts():
    original = t("Jackie", "directed_by", "Pablo Larrain")
    kb = derive_closure([original])
    assert any(x.subject == "jackie" and x.predicate == "directed_by" for x in kb)


def test_closure_keeps_provenance_on_derived_facts():
    kb = derive_closure([t("Jackie", "directed_by", "Pablo Larrain", source="ev42")])
    assert all(x.source == "ev42" for x in kb)


def test_closure_does_not_invent_inverses_for_unknown_predicates():
    kb = derive_closure([t("X", "vaguely_relates_to", "Y")])
    assert len(kb) == 1


# --- scoring: support -------------------------------------------------------

def test_exact_match_supports():
    kb = derive_closure([t("Jackie", "directed_by", "Pablo Larrain")])
    score, rule, sources = score_triple(t("Jackie", "directed_by", "Pablo Larrain"), kb)
    assert score == SUPPORT and rule == "entailment"
    assert sources == ["e1"]


def test_support_survives_surface_differences():
    kb = derive_closure([t("The Chrysler Building", "located_in", "New York City")])
    score, _, _ = score_triple(t("Chrysler Building", "located_in", "new york city."), kb)
    assert score == SUPPORT


def test_support_via_a_derived_inverse_fact():
    """Evidence says the film was directed_by the person; the argument states the
    person directed the film. Only the closure connects them."""
    kb = derive_closure([t("Jackie", "directed_by", "Pablo Larrain")])
    score, rule, _ = score_triple(t("Pablo Larrain", "directed", "Jackie"), kb)
    assert score == SUPPORT and rule == "entailment"


# --- scoring: contradiction -------------------------------------------------

def test_functional_predicate_with_a_different_object_contradicts():
    kb = derive_closure([t("Jackie", "directed_by", "Pablo Larrain")])
    score, rule, _ = score_triple(t("Jackie", "directed_by", "Peter Jackson"), kb)
    assert score == CONTRADICT and rule == "functional_contradiction"


def test_non_functional_predicate_with_a_different_object_does_not_contradict():
    """A film can have many actors, so two different objects are not a conflict.
    Firing here would be the single easiest way to manufacture false contradictions."""
    kb = derive_closure([t("Jackie", "starred", "Natalie Portman")])
    score, rule, _ = score_triple(t("Jackie", "starred", "Greta Gerwig"), kb)
    assert score == 0.0 and rule == "no_symbolic_match"


def test_negation_mismatch_contradicts():
    kb = derive_closure([t("Sydney", "capital_of", "Australia", negated=True)])
    score, rule, _ = score_triple(t("Sydney", "capital_of", "Australia"), kb)
    assert score == CONTRADICT and rule == "negation"


def test_matching_negations_support_each_other():
    kb = derive_closure([t("Sydney", "capital_of", "Australia", negated=True)])
    score, _, _ = score_triple(t("Sydney", "capital_of", "Australia", negated=True), kb)
    assert score == SUPPORT


def test_numeric_mismatch_contradicts():
    kb = derive_closure([t("Chrysler Building", "height", "319 metres")])
    score, rule, _ = score_triple(t("Chrysler Building", "height", "443 metres"), kb)
    assert score == CONTRADICT and rule == "numeric_mismatch"


def test_matching_numbers_support():
    kb = derive_closure([t("Chrysler Building", "height", "319 metres")])
    score, _, _ = score_triple(t("Chrysler Building", "height", "319 m"), kb)
    assert score == SUPPORT


# --- scoring: abstention ----------------------------------------------------

def test_unknown_subject_abstains_rather_than_guessing():
    kb = derive_closure([t("Jackie", "directed_by", "Pablo Larrain")])
    score, rule, sources = score_triple(t("Some Other Film", "directed_by", "Anyone"), kb)
    assert score == 0.0 and rule == "no_symbolic_match" and sources == []


def test_empty_kb_abstains():
    score, rule, _ = score_triple(t("Jackie", "directed_by", "Pablo Larrain"), [])
    assert score == 0.0 and rule == "no_symbolic_match"


def test_contradiction_wins_over_support_when_evidence_conflicts():
    """Two evidence sentences disagree. Reporting support would silently hide a
    known conflict, so the contradiction must surface."""
    kb = derive_closure([
        t("Jackie", "directed_by", "Pablo Larrain", source="e1"),
        t("Jackie", "directed_by", "Peter Jackson", source="e2"),
    ])
    score, rule, _ = score_triple(t("Jackie", "directed_by", "Pablo Larrain"), kb)
    assert score == CONTRADICT and rule == "functional_contradiction"


def test_score_is_bounded():
    kb = derive_closure([t("A", "directed_by", "B")])
    for probe in (t("A", "directed_by", "B"), t("A", "directed_by", "C"), t("Z", "p", "q")):
        score, _, _ = score_triple(probe, kb)
        assert -1.0 <= score <= 1.0


def test_triple_with_missing_parts_abstains():
    kb = derive_closure([t("A", "directed_by", "B")])
    for bad in (t("", "directed_by", "B"), t("A", "", "B"), t("A", "directed_by", "")):
        score, rule, _ = score_triple(bad, kb)
        assert score == 0.0 and rule == "no_symbolic_match"
