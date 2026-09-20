"""Multi-argument turns with free attack targeting (spec §4.3).

The old protocol emitted one argument per turn, each implicitly attacking the
previous one, so every debate produced the same chain and the grounded extension
was a constant. These tests pin the properties that make the graph vary.
"""
import json
from unittest.mock import patch

import pytest

from app.services.orchestrator import MAX_ARGUMENTS, MAX_PER_TURN, run_debate, valid_attacks
from app.models.schemas import Argument


def _arg(i, agent):
    return Argument(id=f"arg_{i}", agent=agent, round=1, text="t", attacks=[], self_confidence=0.5)


def turn(*args, concede=False):
    """Build a new-shape turn response."""
    return json.dumps({
        "concede": concede,
        "arguments": [
            {"argument_text": text, "attacks": attacks, "confidence": conf}
            for text, attacks, conf in args
        ],
    })


# --- attack validation ------------------------------------------------------

PRIOR = [_arg(1, "advocate"), _arg(2, "skeptic"), _arg(3, "advocate")]


def test_valid_attacks_keeps_opposing_prior_arguments():
    assert valid_attacks(["arg_1", "arg_3"], "skeptic", PRIOR) == ["arg_1", "arg_3"]


def test_valid_attacks_drops_same_side_targets():
    """An advocate attacking an advocate is incoherent in a two-sided debate and
    would let a side dismantle its own case to game the grounded extension."""
    assert valid_attacks(["arg_1", "arg_2"], "skeptic", PRIOR) == ["arg_1", "arg_3"][:1]


def test_valid_attacks_drops_unknown_and_forward_references():
    assert valid_attacks(["arg_99", "nonsense", "arg_1"], "skeptic", PRIOR) == ["arg_1"]


def test_valid_attacks_dedupes():
    assert valid_attacks(["arg_1", "arg_1"], "skeptic", PRIOR) == ["arg_1"]


def test_valid_attacks_on_empty_prior_is_empty():
    assert valid_attacks(["arg_1"], "advocate", []) == []


def test_valid_attacks_tolerates_junk_input():
    assert valid_attacks(None, "skeptic", PRIOR) == []
    assert valid_attacks("arg_1", "skeptic", PRIOR) == ["arg_1"]   # bare string
    assert valid_attacks([None, 7, ""], "skeptic", PRIOR) == []


# --- multi-argument turns ---------------------------------------------------

@patch("app.services.orchestrator.call_grok")
def test_turn_can_emit_several_arguments(mock_grok):
    mock_grok.side_effect = [
        turn(("A1", [], 0.9), ("A2", [], 0.8)),
        turn(("S1", ["arg_1"], 0.7), ("S2", ["arg_2"], 0.6)),
    ]
    transcript = run_debate("claim", rounds=1)
    assert [a.id for a in transcript] == ["arg_1", "arg_2", "arg_3", "arg_4"]
    assert [a.agent for a in transcript] == ["advocate"] * 2 + ["skeptic"] * 2
    assert transcript[2].attacks == ["arg_1"]


@patch("app.services.orchestrator.call_grok")
def test_an_argument_can_attack_several_targets(mock_grok):
    mock_grok.side_effect = [
        turn(("A1", [], 0.9), ("A2", [], 0.8)),
        turn(("S1", ["arg_1", "arg_2"], 0.7)),
    ]
    transcript = run_debate("claim", rounds=1)
    assert transcript[2].attacks == ["arg_1", "arg_2"]


@patch("app.services.orchestrator.call_grok")
def test_an_argument_can_attack_an_older_target_not_just_the_last(mock_grok):
    """The whole point of free targeting: without it the graph is a chain."""
    mock_grok.side_effect = [
        turn(("A1", [], 0.9)),
        turn(("S1", ["arg_1"], 0.7)),
        turn(("A2", [], 0.8)),
        turn(("S2", ["arg_1"], 0.6)),   # reaches back past arg_3
    ]
    transcript = run_debate("claim", rounds=2)
    assert transcript[3].attacks == ["arg_1"]


@patch("app.services.orchestrator.call_grok")
def test_an_argument_may_attack_nothing(mock_grok):
    mock_grok.side_effect = [turn(("A1", [], 0.9)), turn(("S1", [], 0.7))]
    transcript = run_debate("claim", rounds=1)
    assert all(a.attacks == [] for a in transcript)


@patch("app.services.orchestrator.call_grok")
def test_same_side_attack_is_stripped_end_to_end(mock_grok):
    mock_grok.side_effect = [
        turn(("A1", [], 0.9), ("A2", ["arg_1"], 0.8)),   # advocate attacks advocate
        turn(("S1", ["arg_1"], 0.7)),
    ]
    transcript = run_debate("claim", rounds=1)
    assert transcript[1].attacks == []


# --- caps -------------------------------------------------------------------

@patch("app.services.orchestrator.call_grok")
def test_arguments_per_turn_are_capped(mock_grok):
    many = tuple((f"A{i}", [], 0.5) for i in range(10))
    mock_grok.side_effect = [turn(*many), turn(("S1", [], 0.5))]
    transcript = run_debate("claim", rounds=1)
    assert sum(1 for a in transcript if a.agent == "advocate") == MAX_PER_TURN


@patch("app.services.orchestrator.call_grok")
def test_total_arguments_are_capped(mock_grok):
    three = (("x", [], 0.5),) * MAX_PER_TURN
    mock_grok.side_effect = [turn(*three) for _ in range(12)]
    transcript = run_debate("claim", rounds=6)
    assert len(transcript) <= MAX_ARGUMENTS


# --- backward compatibility -------------------------------------------------

@patch("app.services.orchestrator.call_grok")
def test_old_single_argument_shape_still_parses(mock_grok):
    """The model sometimes ignores the requested shape. Accepting the old one is
    cheaper than burning a retry, and keeps the existing regression tests honest."""
    mock_grok.side_effect = [
        '{"argument_text": "A1", "attacks_argument_id": null, "confidence": 0.9, "concede": false}',
        '{"argument_text": "S1", "attacks_argument_id": "arg_1", "confidence": 0.8, "concede": false}',
    ]
    transcript = run_debate("claim", rounds=1)
    assert [a.text for a in transcript] == ["A1", "S1"]
    assert transcript[1].attacks == ["arg_1"]


@patch("app.services.orchestrator.call_grok")
def test_turn_with_no_usable_arguments_counts_as_concede(mock_grok):
    mock_grok.side_effect = [
        turn(),                              # advocate: empty list
        turn(("S1", [], 0.7)),
    ]
    transcript = run_debate("claim", rounds=1)
    assert [a.agent for a in transcript] == ["skeptic"]


@patch("app.services.orchestrator.call_grok")
def test_confidence_is_clamped_per_argument(mock_grok):
    mock_grok.side_effect = [
        turn(("A1", [], 5.0), ("A2", [], -3.0)),
        turn(("S1", [], 0.5)),
    ]
    transcript = run_debate("claim", rounds=1)
    assert transcript[0].self_confidence == 1.0
    assert transcript[1].self_confidence == 0.0


# --- the property that actually matters -------------------------------------

@patch("app.services.orchestrator.call_grok")
def test_protocol_can_produce_a_non_chain_graph(mock_grok):
    """The regression this whole phase exists to prevent: under the old protocol
    every debate produced arg1<-arg2<-arg3<-arg4 and the grounded extension was
    always skeptic-2 / advocate-0. Here two arguments attack the same target and
    one argument is attacked twice, so the graph is not a path."""
    mock_grok.side_effect = [
        turn(("A1", [], 0.9), ("A2", [], 0.8)),
        turn(("S1", ["arg_1"], 0.7), ("S2", ["arg_1", "arg_2"], 0.6)),
    ]
    transcript = run_debate("claim", rounds=1)

    targets = [t for a in transcript for t in a.attacks]
    assert targets.count("arg_1") == 2   # in-degree 2: impossible in a path


@patch("app.services.orchestrator.call_grok")
def test_grounded_extension_can_escape_the_degenerate_constant(mock_grok):
    """Under the old protocol the grounded extension was skeptic-2 / advocate-0 in
    57 of 58 recorded debates, so the structural signal was a constant.

    Free targeting makes other outcomes reachable: here the round-2 skeptic
    reaches back to an already-defeated argument instead of rebutting the live
    one, so an advocate argument survives.

    Note this does NOT by itself guarantee variety - whoever speaks last is still
    never attacked. That residual bias is what the evidence weighting in spec
    §4.5 removes.
    """
    from app.services.semantics_engine import compute_grounded_extension

    mock_grok.side_effect = [
        turn(("A1", [], 0.9)),              # arg_1
        turn(("S1", ["arg_1"], 0.7)),       # arg_2 -> arg_1
        turn(("A2", ["arg_2"], 0.8)),       # arg_3 -> arg_2
        turn(("S2", ["arg_1"], 0.6)),       # arg_4 -> arg_1 (reaches back)
    ]
    grounded = compute_grounded_extension(run_debate("claim", rounds=2))

    assert grounded["advocate"] == ["arg_3"]
    assert grounded["skeptic"] == ["arg_4"]
    # The old protocol could only ever produce advocate 0 / skeptic 2.
    assert len(grounded["advocate"]) - len(grounded["skeptic"]) == 0
