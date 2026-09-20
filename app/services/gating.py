"""Evidence-gated attack edges (spec §4.4).

An asserted attack only becomes an edge in the argumentation framework if the
attacker itself is supported by retrieved evidence. This is what chains M4
(reasoning over evidence) into M3 (the argumentation graph): without it the
graph is a record of who said what, and its grounded extension is decided by
turn order rather than by whether anything said was true.

Dropped edges are returned rather than discarded. "This agent attacked but had
nothing behind it" belongs in the trace — it is the visible evidence that the
graph follows the evidence.
"""
from typing import List, Tuple

from app.models.schemas import Argument, FactCheckResult

# A floor, not a strict threshold: an argument the rules could not decide scores
# exactly 0.0, and stripping those would leave an edgeless graph on every debate
# whose evidence could not be retrieved.
DEFAULT_TAU = 0.0


def gate_attacks(
    arguments: List[Argument],
    fact_results: List[FactCheckResult],
    tau: float = DEFAULT_TAU,
) -> Tuple[List[Argument], List[Tuple[str, str]]]:
    """Filter attack edges by the attacker's evidence support.

    Returns (arguments with gated attack lists, dropped (source, target) edges).
    Arguments are never removed — only their edges — so the transcript a reader
    sees is always the full debate.

    ``tau=-1.0`` admits every edge, which is how the no-gating ablation runs.
    """
    support = {r.argument_id: r.support_score for r in fact_results}

    gated, dropped = [], []
    for a in arguments:
        # An argument nobody scored is neutral, not unsupported: treating a
        # missing score as a failure would silently gut debates whose fact-check
        # call failed.
        score = support.get(a.id, 0.0)
        if a.attacks and score < tau:
            dropped.extend((a.id, t) for t in a.attacks)
            gated.append(a.model_copy(update={"attacks": []}))
        else:
            gated.append(a.model_copy())

    return gated, dropped
