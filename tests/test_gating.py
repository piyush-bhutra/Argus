"""Evidence-gated attack edges (spec §4.4). Pure, no LLM."""
import pytest

from app.models.schemas import Argument, FactCheckResult
from app.services.gating import DEFAULT_TAU, gate_attacks


def arg(i, agent, attacks=()):
    return Argument(id=f"arg_{i}", agent=agent, round=1, text="t",
                    attacks=list(attacks), self_confidence=0.5)


def fc(i, score, method="symbolic"):
    return FactCheckResult(argument_id=f"arg_{i}", evidence_sentences=[],
                           support_score=score, method=method)


def test_supported_attacker_keeps_its_edge():
    args = [arg(1, "advocate"), arg(2, "skeptic", ["arg_1"])]
    gated, dropped = gate_attacks(args, [fc(2, 1.0)])
    assert gated[1].attacks == ["arg_1"]
    assert dropped == []


def test_contradicted_attacker_loses_its_edge():
    args = [arg(1, "advocate"), arg(2, "skeptic", ["arg_1"])]
    gated, dropped = gate_attacks(args, [fc(2, -1.0)])
    assert gated[1].attacks == []
    assert dropped == [("arg_2", "arg_1")]


def test_attacker_exactly_at_tau_is_admitted():
    """tau is a floor, not a strict threshold: an abstaining argument (0.0) must
    not be silently stripped of every attack it makes, or a debate with no
    retrievable evidence would produce an edgeless graph."""
    args = [arg(1, "advocate"), arg(2, "skeptic", ["arg_1"])]
    gated, dropped = gate_attacks(args, [fc(2, DEFAULT_TAU)])
    assert gated[1].attacks == ["arg_1"]


def test_unscored_attacker_is_treated_as_neutral_and_admitted():
    args = [arg(1, "advocate"), arg(2, "skeptic", ["arg_1"])]
    gated, _ = gate_attacks(args, [])
    assert gated[1].attacks == ["arg_1"]


def test_tau_is_configurable():
    args = [arg(1, "advocate"), arg(2, "skeptic", ["arg_1"])]
    assert gate_attacks(args, [fc(2, 0.4)], tau=0.5)[0][1].attacks == []
    assert gate_attacks(args, [fc(2, 0.4)], tau=0.3)[0][1].attacks == ["arg_1"]


def test_tau_minus_one_admits_everything():
    """This is how the 'no gating' ablation is run (spec §5.3)."""
    args = [arg(1, "advocate"), arg(2, "skeptic", ["arg_1"])]
    gated, dropped = gate_attacks(args, [fc(2, -1.0)], tau=-1.0)
    assert gated[1].attacks == ["arg_1"]
    assert dropped == []


def test_gating_only_drops_edges_never_arguments():
    args = [arg(1, "advocate"), arg(2, "skeptic", ["arg_1"])]
    gated, _ = gate_attacks(args, [fc(2, -1.0)])
    assert [a.id for a in gated] == ["arg_1", "arg_2"]


def test_gating_does_not_mutate_the_input():
    args = [arg(1, "advocate"), arg(2, "skeptic", ["arg_1"])]
    gate_attacks(args, [fc(2, -1.0)])
    assert args[1].attacks == ["arg_1"]


def test_partial_gating_keeps_the_supported_targets():
    args = [arg(1, "advocate"), arg(2, "advocate"), arg(3, "skeptic", ["arg_1", "arg_2"])]
    gated, dropped = gate_attacks(args, [fc(3, -1.0)])
    # The attacker is contradicted, so it loses ALL of its edges, not some.
    assert gated[2].attacks == []
    assert set(dropped) == {("arg_3", "arg_1"), ("arg_3", "arg_2")}


def test_gating_changes_the_grounded_extension():
    """The point of gating: an unsupported attack no longer defeats a supported
    argument, so the graph follows the evidence rather than the rhetoric."""
    from app.services.semantics_engine import compute_grounded_extension

    args = [arg(1, "advocate"), arg(2, "skeptic", ["arg_1"])]
    ungated = compute_grounded_extension(args)
    assert ungated == {"advocate": [], "skeptic": ["arg_2"]}

    gated, _ = gate_attacks(args, [fc(2, -1.0)])
    assert compute_grounded_extension(gated) == {
        "advocate": ["arg_1"], "skeptic": ["arg_2"],
    }
