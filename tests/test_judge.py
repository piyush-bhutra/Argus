import pytest
from app.services.judge import compute_raw_probability, fit_calibrator, apply_calibration
from app.models.schemas import Argument, FactCheckResult

def test_compute_raw_probability_worked_example():
    grounded_extension = {
        "advocate": ["a1", "a2"],
        "skeptic": []
    }
    
    fact_check_results = [
        FactCheckResult(argument_id="a1", evidence_sentences=[], support_score=0.5),
        FactCheckResult(argument_id="s1", evidence_sentences=[], support_score=-0.5)
    ]
    
    arguments = [
        Argument(id="a1", agent="advocate", round=1, text="text", attacks=[], self_confidence=0.8),
        Argument(id="a2", agent="advocate", round=1, text="text", attacks=[], self_confidence=0.8),
        Argument(id="s1", agent="skeptic", round=1, text="text", attacks=[], self_confidence=0.6)
    ]
    
    raw_prob = compute_raw_probability(grounded_extension, fact_check_results, arguments)
    
    # expected raw_probability = sigmoid(2 + 1.0 + 0.1) = sigmoid(3.1) ≈ 0.9569
    assert raw_prob == pytest.approx(0.9569, abs=0.001)

def test_compute_raw_probability_zero_signal():
    grounded_extension = {
        "advocate": [],
        "skeptic": []
    }
    
    fact_check_results = []
    
    arguments = [
        Argument(id="a1", agent="advocate", round=1, text="text", attacks=[], self_confidence=0.0),
        Argument(id="s1", agent="skeptic", round=1, text="text", attacks=[], self_confidence=0.0)
    ]
    
    raw_prob = compute_raw_probability(grounded_extension, fact_check_results, arguments)
    
    assert raw_prob == 0.5

def test_calibration_monotonicity_and_bounds():
    raw_probabilities = [0.1, 0.3, 0.5, 0.7, 0.9]
    true_labels = [False, False, True, True, True]
    
    calibrator = fit_calibrator(raw_probabilities, true_labels)
    
    prev_val = -1.0
    for p in raw_probabilities:
        cal_p = apply_calibration(calibrator, p)
        assert 0.0 <= cal_p <= 1.0
        assert cal_p >= prev_val
        prev_val = cal_p
