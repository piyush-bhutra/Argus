import pytest
from app.models.schemas import Argument
from app.services.semantics_engine import _compute_labeling, compute_grounded_extension

def test_grounded_extension_reinstatement():
    """
    Case 1: Reinstatement: C attacks A, A attacks B, C has no attackers.
    Expected: C=IN, A=OUT, B=IN.
    """
    arguments = [
        Argument(id="C", agent="advocate", round=1, text="C", attacks=["A"], self_confidence=1.0),
        Argument(id="A", agent="skeptic", round=1, text="A", attacks=["B"], self_confidence=1.0),
        Argument(id="B", agent="advocate", round=1, text="B", attacks=[], self_confidence=1.0)
    ]
    labels = _compute_labeling(arguments)
    assert labels == {"C": "IN", "A": "OUT", "B": "IN"}
    
    # Also verify external behavior
    result = compute_grounded_extension(arguments)
    assert set(result["advocate"]) == {"C", "B"}
    assert set(result["skeptic"]) == set()

def test_grounded_extension_cycle():
    """
    Case 2: Cycle: A attacks B, B attacks A, no other attackers.
    Expected: A=UNDEC, B=UNDEC.
    """
    arguments = [
        Argument(id="A", agent="advocate", round=1, text="A", attacks=["B"], self_confidence=1.0),
        Argument(id="B", agent="skeptic", round=1, text="B", attacks=["A"], self_confidence=1.0)
    ]
    labels = _compute_labeling(arguments)
    assert labels == {"A": "UNDEC", "B": "UNDEC"}
    
    # Verify external behavior
    result = compute_grounded_extension(arguments)
    assert set(result["advocate"]) == set()
    assert set(result["skeptic"]) == set()

def test_grounded_extension_simple_defeat():
    """
    Case 3: Simple defeat: A attacks B, A has no attackers.
    Expected: A=IN, B=OUT.
    """
    arguments = [
        Argument(id="A", agent="advocate", round=1, text="A", attacks=["B"], self_confidence=1.0),
        Argument(id="B", agent="skeptic", round=1, text="B", attacks=[], self_confidence=1.0)
    ]
    labels = _compute_labeling(arguments)
    assert labels == {"A": "IN", "B": "OUT"}
    
    # Verify external behavior
    result = compute_grounded_extension(arguments)
    assert set(result["advocate"]) == {"A"}
    assert set(result["skeptic"]) == set()
