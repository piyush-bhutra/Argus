"""
PRD §5d - Fact-Checking / KB Chaining Module
"""
from app.models.schemas import FactCheckResult

def check_argument(argument_text: str) -> FactCheckResult:
    """
    Stub for fact-check/KB forward-chaining module.
    Returns a dummy FactCheckResult.
    """
    return FactCheckResult(
        argument_id="dummy_arg_id",
        evidence_sentences=["The sky is blue."],
        support_score=0.8
    )
