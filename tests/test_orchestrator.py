import pytest
from unittest.mock import patch
from app.services.orchestrator import run_debate

@patch("app.services.orchestrator.call_grok")
def test_normal_debate(mock_call_grok):
    mock_call_grok.side_effect = [
        '{"argument_text": "A1", "attacks_argument_id": null, "confidence": 0.9, "concede": false}',
        '{"argument_text": "S1", "attacks_argument_id": "arg_1", "confidence": 0.8, "concede": false}',
        '{"argument_text": "A2", "attacks_argument_id": "arg_2", "confidence": 0.85, "concede": false}',
        '{"argument_text": "S2", "attacks_argument_id": "arg_3", "confidence": 0.75, "concede": false}',
        '{"argument_text": "A3", "attacks_argument_id": "arg_4", "confidence": 0.95, "concede": false}',
        '{"argument_text": "S3", "attacks_argument_id": "arg_5", "confidence": 0.8, "concede": false}',
    ]
    
    transcript = run_debate("Test claim", rounds=3)
    
    assert len(transcript) == 6
    assert transcript[0].id == "arg_1"
    assert transcript[0].agent == "advocate"
    assert transcript[0].round == 1
    assert transcript[1].id == "arg_2"
    assert transcript[1].agent == "skeptic"
    assert transcript[1].attacks == ["arg_1"]
    assert transcript[5].id == "arg_6"
    assert transcript[5].agent == "skeptic"
    assert transcript[5].attacks == ["arg_5"]
    assert transcript[5].round == 3

@patch("app.services.orchestrator.call_grok")
def test_malformed_json_recovery(mock_call_grok):
    mock_call_grok.side_effect = [
        'bad json',
        '{"argument_text": "A1", "attacks_argument_id": null, "confidence": 1.5, "concede": false}',
        '{"concede": true}'
    ]
    
    transcript = run_debate("Test claim", rounds=1)
    
    assert len(transcript) == 1
    assert transcript[0].id == "arg_1"
    assert transcript[0].text == "A1"
    # confidence should be clamped to 1.0
    assert transcript[0].self_confidence == 1.0

@patch("app.services.orchestrator.call_grok")
def test_retries_exhausted_concede(mock_call_grok):
    mock_call_grok.side_effect = [
        'bad json 1', 'bad json 2', 'bad json 3',   # advocate, round 1
        'bad json 4', 'bad json 5', 'bad json 6',   # skeptic, round 1
    ]

    transcript = run_debate("Test claim", rounds=1)

    # Both agents exhaust retries (treated as concession) -> empty transcript,
    # but the skeptic is still given its turn first.
    assert len(transcript) == 0
    assert mock_call_grok.call_count == 6

@patch("app.services.orchestrator.call_grok")
def test_on_argument_streams_each_turn(mock_call_grok):
    mock_call_grok.side_effect = [
        '{"argument_text": "A1", "attacks_argument_id": null, "confidence": 0.9, "concede": false}',
        '{"argument_text": "S1", "attacks_argument_id": "arg_1", "confidence": 0.8, "concede": false}',
    ]

    snapshots = []
    transcript = run_debate(
        "Test claim", rounds=1, on_argument=lambda t: snapshots.append([a.id for a in t])
    )

    # Called once per argument, with a growing transcript each time.
    assert snapshots == [["arg_1"], ["arg_1", "arg_2"]]
    assert len(transcript) == 2


@patch("app.services.orchestrator.call_grok")
def test_advocate_concedes_turn_one_skeptic_still_speaks(mock_call_grok):
    """Regression: Advocate conceding on its very first turn must NOT skip the
    Skeptic's opening argument (PROJECT_STATE §5 Bug 1)."""
    mock_call_grok.side_effect = [
        '{"concede": true}',
        '{"argument_text": "S1", "attacks_argument_id": null, "confidence": 0.7, "concede": false}',
    ]

    transcript = run_debate("Test claim", rounds=1)

    assert len(transcript) == 1
    assert transcript[0].agent == "skeptic"
    assert transcript[0].text == "S1"


@patch("app.services.orchestrator.call_grok")
def test_early_termination_both_concede(mock_call_grok):
    mock_call_grok.side_effect = [
        '{"argument_text": "A1", "attacks_argument_id": null, "confidence": 0.9, "concede": false}',
        '{"argument_text": "S1", "attacks_argument_id": "arg_1", "confidence": 0.8, "concede": false}',
        '{"concede": true}', # Advocate concedes in Round 2
        '{"concede": true}', # Skeptic concedes in Round 2
    ]
    
    transcript = run_debate("Test claim", rounds=3)
    
    # Should terminate after round 2, without padded empty rounds
    assert len(transcript) == 2
    assert transcript[0].id == "arg_1"
    assert transcript[1].id == "arg_2"
