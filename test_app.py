"""End-to-end API smoke test with the LLM layer mocked out."""
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.models.schemas import Argument
from app.services import debate_store

client = TestClient(app)

FAKE_TRANSCRIPT = [
    Argument(id="arg_1", agent="advocate", round=1, text="A1", attacks=[], self_confidence=0.8),
    Argument(id="arg_2", agent="skeptic", round=1, text="S1", attacks=["arg_1"], self_confidence=0.6),
]


def _fake_pipeline(debate_id: str):
    from app.services.pipeline import assemble_verdict, build_graph

    debate_store.set_transcript(debate_id, FAKE_TRANSCRIPT)
    with patch("app.services.pipeline.check_transcript", return_value=[]):
        verdict = assemble_verdict(
            debate_store.get(debate_id).claim, FAKE_TRANSCRIPT, calibrator=None
        )
    debate_store.set_result(debate_id, verdict, build_graph(FAKE_TRANSCRIPT))


def test_full_debate_flow():
    with patch("app.api.routes.run_pipeline", side_effect=_fake_pipeline):
        start = client.post("/debate/start", json={"claim": "The sky is blue.", "rounds": 2})
        assert start.status_code == 200
        debate_id = start.json()["debate_id"]

        transcript = client.get(f"/debate/{debate_id}/transcript")
        assert transcript.status_code == 200
        assert transcript.json()["status"] == "complete"
        assert len(transcript.json()["arguments"]) == 2

        graph = client.get(f"/debate/{debate_id}/graph")
        assert graph.status_code == 200
        node_ids = {n["id"] for n in graph.json()["nodes"]}
        assert node_ids == {"arg_1", "arg_2"}
        assert all("agent" in n and "round" in n for n in graph.json()["nodes"])

        verdict = client.get(f"/debate/{debate_id}/verdict")
        assert verdict.status_code == 200
        body = verdict.json()
        assert 0.0 <= body["raw_probability"] <= 1.0
        assert "grounded_extension" in body


def test_unknown_debate_id_is_404():
    assert client.get("/debate/nope/transcript").status_code == 404
    assert client.get("/debate/nope/verdict").status_code == 404
    assert client.get("/debate/nope/graph").status_code == 404


def test_empty_claim_rejected():
    assert client.post("/debate/start", json={"claim": "   "}).status_code == 422
