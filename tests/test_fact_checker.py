from unittest.mock import patch

from app.models.schemas import Argument
from app.services.fact_checker import check_transcript

ARGS = [
    Argument(id="arg_1", agent="advocate", round=1, text="Water boils at 100C at sea level.", attacks=[], self_confidence=0.9),
    Argument(id="arg_2", agent="skeptic", round=1, text="The moon is made of cheese.", attacks=["arg_1"], self_confidence=0.4),
]


@patch("app.services.fact_checker.call_grok")
def test_check_transcript_parses_scores(mock_call_grok):
    mock_call_grok.return_value = """```json
    {"results": [
        {"argument_id": "arg_1", "support_score": 0.9, "reasoning": "Well established."},
        {"argument_id": "arg_2", "support_score": -1.0, "reasoning": "Contradicted."}
    ]}
    ```"""

    results = check_transcript("test claim", ARGS)

    assert [r.argument_id for r in results] == ["arg_1", "arg_2"]
    assert results[0].support_score == 0.9
    assert results[1].support_score == -1.0
    assert results[0].evidence_sentences == ["Well established."]


@patch("app.services.fact_checker.call_grok")
def test_check_transcript_malformed_falls_back_to_neutral(mock_call_grok):
    mock_call_grok.return_value = "sorry, I cannot do that"

    results = check_transcript("test claim", ARGS)

    assert len(results) == 2
    assert all(r.support_score == 0.0 for r in results)
    assert all(r.evidence_sentences == [] for r in results)


@patch("app.services.fact_checker.call_grok")
def test_check_transcript_api_error_falls_back(mock_call_grok):
    mock_call_grok.side_effect = RuntimeError("boom")

    results = check_transcript("test claim", ARGS)

    assert [r.argument_id for r in results] == ["arg_1", "arg_2"]
    assert all(r.support_score == 0.0 for r in results)


def test_check_transcript_empty():
    assert check_transcript("test claim", []) == []
