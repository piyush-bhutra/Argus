from unittest.mock import patch

from app.models.schemas import Argument, FactCheckResult
from app.services import debate_store
from app.services.pipeline import assemble_verdict, build_graph, run_pipeline

TRANSCRIPT = [
    Argument(id="arg_1", agent="advocate", round=1, text="A1", attacks=[], self_confidence=0.8),
    Argument(id="arg_2", agent="skeptic", round=1, text="S1", attacks=["arg_1"], self_confidence=0.6),
    Argument(id="arg_3", agent="advocate", round=2, text="A2", attacks=["arg_2"], self_confidence=0.7),
]


def test_build_graph_shape():
    graph = build_graph(TRANSCRIPT)
    assert {n.id for n in graph.nodes} == {"arg_1", "arg_2", "arg_3"}
    assert all(n.agent in ("advocate", "skeptic") for n in graph.nodes)
    assert {(e.source, e.target) for e in graph.edges} == {("arg_2", "arg_1"), ("arg_3", "arg_2")}


def test_build_graph_drops_dangling_edges():
    args = [Argument(id="arg_1", agent="advocate", round=1, text="x", attacks=["ghost"], self_confidence=0.5)]
    assert build_graph(args).edges == []


@patch("app.services.pipeline.check_transcript")
def test_assemble_verdict_no_calibrator(mock_fc):
    mock_fc.return_value = [
        FactCheckResult(argument_id="arg_1", evidence_sentences=[], support_score=0.5),
        FactCheckResult(argument_id="arg_2", evidence_sentences=[], support_score=-0.2),
        FactCheckResult(argument_id="arg_3", evidence_sentences=[], support_score=0.3),
    ]

    verdict = assemble_verdict("Some claim", TRANSCRIPT, calibrator=None)

    assert verdict.claim == "Some claim"
    assert 0.0 <= verdict.raw_probability <= 1.0
    assert verdict.calibrated_probability == verdict.raw_probability
    assert "advocate" in verdict.grounded_extension
    assert verdict.explanation


@patch("app.services.pipeline._load_calibrator", return_value=None)
@patch("app.services.pipeline.check_transcript")
@patch("app.services.pipeline.run_debate")
def test_run_pipeline_updates_store(mock_run_debate, mock_fc, _mock_cal):
    mock_run_debate.return_value = TRANSCRIPT
    mock_fc.return_value = [
        FactCheckResult(argument_id=a.id, evidence_sentences=[], support_score=0.0)
        for a in TRANSCRIPT
    ]

    debate_id = debate_store.create("Pipeline claim", rounds=2)
    run_pipeline(debate_id)

    record = debate_store.get(debate_id)
    assert record.status == "complete"
    assert len(record.transcript) == 3
    assert record.verdict is not None
    assert record.graph is not None


@patch("app.services.pipeline.run_debate", side_effect=RuntimeError("llm down"))
def test_run_pipeline_records_error(_mock_run_debate):
    debate_id = debate_store.create("Doomed claim", rounds=2)
    run_pipeline(debate_id)

    record = debate_store.get(debate_id)
    assert record.status == "error"
    assert "llm down" in record.error
