"""Evidence-weighted structural term (spec §4.5). Pure math, no LLM."""
import math

import pytest

from app.models.schemas import Argument, FactCheckResult
from app.services.judge import compute_raw_probability, structural_signal


def arg(i, agent, conf=0.5):
    return Argument(id=f"arg_{i}", agent=agent, round=1, text="t",
                    attacks=[], self_confidence=conf)


def fc(i, score):
    return FactCheckResult(argument_id=f"arg_{i}", evidence_sentences=[], support_score=score)


# --- the structural term ----------------------------------------------------

def test_structural_is_bounded_in_minus_one_to_one():
    cases = [
        ({"advocate": ["arg_1"], "skeptic": []}, [fc(1, 1.0)]),
        ({"advocate": [], "skeptic": ["arg_1"]}, [fc(1, 1.0)]),
        ({"advocate": ["arg_1"], "skeptic": ["arg_2"]}, [fc(1, 1.0), fc(2, -1.0)]),
    ]
    for grounded, facts in cases:
        assert -1.0 <= structural_signal(grounded, facts) <= 1.0


def test_supported_advocate_survivor_favours_the_claim():
    g = {"advocate": ["arg_1"], "skeptic": []}
    assert structural_signal(g, [fc(1, 1.0)]) == 1.0


def test_supported_skeptic_survivor_opposes_the_claim():
    g = {"advocate": [], "skeptic": ["arg_1"]}
    assert structural_signal(g, [fc(1, 1.0)]) == -1.0


def test_a_survivor_with_no_evidence_contributes_nothing():
    """This is the last-speaker fix. The final argument is never attacked, so it
    always survives; if no evidence backs it, it must not move the verdict."""
    g = {"advocate": [], "skeptic": ["arg_1"]}
    assert structural_signal(g, [fc(1, 0.0)]) == 0.0


def test_the_old_degenerate_case_now_scores_zero():
    """57 of 58 recorded debates produced exactly this: skeptic 2, advocate 0.
    The old judge turned it into a constant -2 on the logit. With no evidence
    behind those survivors it must now be neutral."""
    g = {"advocate": [], "skeptic": ["arg_2", "arg_4"]}
    assert structural_signal(g, [fc(2, 0.0), fc(4, 0.0)]) == 0.0


def test_a_contradicted_skeptic_survivor_favours_the_claim():
    """Surviving the graph while the evidence contradicts you should count
    against your side, not for it."""
    g = {"advocate": [], "skeptic": ["arg_1"]}
    assert structural_signal(g, [fc(1, -1.0)]) == 1.0


def test_evenly_matched_supported_survivors_cancel():
    g = {"advocate": ["arg_1"], "skeptic": ["arg_2"]}
    assert structural_signal(g, [fc(1, 1.0), fc(2, 1.0)]) == 0.0


def test_stronger_evidence_outweighs_more_survivors():
    """Count alone would give the skeptic 2-1. Weighted by evidence, the single
    well-supported advocate argument wins."""
    g = {"advocate": ["arg_1"], "skeptic": ["arg_2", "arg_3"]}
    facts = [fc(1, 1.0), fc(2, 0.1), fc(3, 0.1)]
    assert structural_signal(g, facts) > 0


def test_no_survivors_is_neutral():
    assert structural_signal({"advocate": [], "skeptic": []}, []) == 0.0


def test_missing_fact_results_are_neutral_not_crashing():
    g = {"advocate": ["arg_1"], "skeptic": ["arg_2"]}
    assert structural_signal(g, []) == 0.0


# --- the full judge ---------------------------------------------------------

def test_probability_stays_in_range():
    g = {"advocate": ["arg_1"], "skeptic": ["arg_2"]}
    args = [arg(1, "advocate", 1.0), arg(2, "skeptic", 0.0)]
    p = compute_raw_probability(g, [fc(1, 1.0), fc(2, -1.0)], args)
    assert 0.0 < p < 1.0


def test_all_signals_zero_gives_one_half():
    """A debate with no evidence and matched confidence must land on maximum
    uncertainty, not on a side. The old judge returned 0.12 here."""
    g = {"advocate": [], "skeptic": []}
    args = [arg(1, "advocate", 0.5), arg(2, "skeptic", 0.5)]
    p = compute_raw_probability(g, [fc(1, 0.0), fc(2, 0.0)], args)
    assert p == pytest.approx(0.5)


def test_the_recorded_degenerate_debate_is_now_neutral():
    """End-to-end version of the bug: the exact shape of 57 of 58 cached debates
    — skeptic survives twice, advocate never, no evidence either way, equal
    confidence — used to yield P(true)=0.12 regardless of the claim."""
    g = {"advocate": [], "skeptic": ["arg_2", "arg_4"]}
    args = [arg(1, "advocate"), arg(2, "skeptic"), arg(3, "advocate"), arg(4, "skeptic")]
    facts = [fc(i, 0.0) for i in (1, 2, 3, 4)]

    p = compute_raw_probability(g, facts, args)
    assert p == pytest.approx(0.5)
    assert p > 1 / (1 + math.exp(2))   # comfortably above the old constant


def test_evidence_can_override_the_structural_signal():
    """Two supported skeptic survivors, but every argument's evidence points the
    advocate's way: the fact-check term must be able to win."""
    g = {"advocate": [], "skeptic": ["arg_2"]}
    args = [arg(1, "advocate"), arg(2, "skeptic")]
    p = compute_raw_probability(g, [fc(1, 1.0), fc(2, 0.05)], args)
    assert p > 0.5
