"""
End-to-end debate pipeline: glue that runs a claim through every built component.

    run_debate (orchestrator, LLM)
        -> compute_grounded_extension (semantics engine)
        -> check_transcript (fact-checker, LLM)
        -> compute_raw_probability (Bayesian judge)
        -> [optional] apply_calibration
        -> Verdict + argument graph
"""
import pickle
from pathlib import Path
from typing import List, Optional

from app.core.logger import logger
from app.models.schemas import Argument, GraphEdge, GraphNode, GraphResponse, Verdict
from app.services import debate_store
from app.services.fact_checker import check_transcript
from app.services.judge import apply_calibration, compute_raw_probability
from app.services.orchestrator import run_debate
from app.services.semantics_engine import compute_grounded_extension

_CALIBRATOR_FILE = Path(__file__).resolve().parents[2] / "data" / "calibrator.pkl"


def _load_calibrator():
    if not _CALIBRATOR_FILE.exists():
        return None
    try:
        with _CALIBRATOR_FILE.open("rb") as fh:
            return pickle.load(fh)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Could not load calibrator: {e}")
        return None


def build_graph(transcript: List[Argument]) -> GraphResponse:
    ids = {a.id for a in transcript}
    nodes = [
        GraphNode(id=a.id, agent=a.agent, round=a.round, label=a.id.upper())
        for a in transcript
    ]
    edges = [
        GraphEdge(source=a.id, target=target)
        for a in transcript
        for target in a.attacks
        if target in ids
    ]
    return GraphResponse(nodes=nodes, edges=edges)


def _build_explanation(
    claim: str,
    grounded: dict,
    raw: float,
    calibrated: float,
    calibrated_applied: bool,
) -> str:
    adv = grounded.get("advocate", [])
    skp = grounded.get("skeptic", [])

    if adv and not skp:
        structural = (
            f"Only advocate arguments ({', '.join(adv)}) survive the grounded "
            f"extension, so the attack graph favours the claim."
        )
    elif skp and not adv:
        structural = (
            f"Only skeptic arguments ({', '.join(skp)}) survive the grounded "
            f"extension, so the attack graph favours rejecting the claim."
        )
    elif adv and skp:
        structural = (
            f"Both sides retain surviving arguments (advocate: {', '.join(adv)}; "
            f"skeptic: {', '.join(skp)}); the structural signal is mixed."
        )
    else:
        structural = (
            "No argument survives the grounded extension (mutual attacks leave "
            "everything undecided); the structural signal is neutral."
        )

    calib_note = (
        f"The raw probability {raw:.2f} is mapped to a calibrated "
        f"{calibrated:.2f} by the isotonic model trained on held-out labels."
        if calibrated_applied
        else (
            f"No trained calibrator is loaded yet (Review-2 work), so the "
            f"calibrated probability equals the raw score, {raw:.2f}."
        )
    )

    return (
        f"Verdict for: \"{claim}\". {structural} Combining that structural signal "
        f"with the fact-check scores and the agents' self-reported confidence, the "
        f"Bayesian judge produces P(claim true) = {raw:.2f}. {calib_note}"
    )


def assemble_verdict(
    claim: str,
    transcript: List[Argument],
    calibrator=None,
    fact_results: Optional[List] = None,
) -> Verdict:
    """Run semantics + fact-check + judge over a finished transcript.

    Pass ``fact_results`` to skip the LLM fact-check call (used by the offline
    demo builder)."""
    grounded = compute_grounded_extension(transcript)
    if fact_results is None:
        fact_results = check_transcript(claim, transcript)
    raw = compute_raw_probability(grounded, fact_results, transcript)

    calibrated_applied = calibrator is not None
    calibrated = apply_calibration(calibrator, raw) if calibrated_applied else raw

    return Verdict(
        claim=claim,
        raw_probability=raw,
        calibrated_probability=calibrated,
        grounded_extension={
            "advocate": grounded.get("advocate", []),
            "skeptic": grounded.get("skeptic", []),
        },
        explanation=_build_explanation(
            claim, grounded, raw, calibrated, calibrated_applied
        ),
    )


def run_pipeline(debate_id: str) -> None:
    """Full pipeline for a stored debate. Intended to run as a background task."""
    record = debate_store.get(debate_id)
    if record is None:
        logger.error(f"run_pipeline: unknown debate_id {debate_id}")
        return

    try:
        logger.info(f"[{debate_id}] starting debate on: {record.claim!r}")
        transcript = run_debate(record.claim, record.rounds)
        debate_store.set_transcript(debate_id, transcript)

        verdict = assemble_verdict(record.claim, transcript, _load_calibrator())
        graph = build_graph(transcript)

        debate_store.set_result(debate_id, verdict, graph)
        logger.info(
            f"[{debate_id}] complete — {len(transcript)} arguments, "
            f"P(true)={verdict.calibrated_probability:.2f}"
        )
    except Exception as e:  # noqa: BLE001
        logger.exception(f"[{debate_id}] pipeline failed")
        debate_store.set_error(debate_id, str(e))
