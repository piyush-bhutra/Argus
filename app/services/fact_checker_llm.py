"""Legacy LLM-as-judge fact-checker, kept ONLY for the ablation (spec §5.3).

This asks the same model that generated the arguments whether those arguments
are true. That circularity is why it supplied no information the debate did not
already contain, and it is what app/services/fact_checker.py replaced.

It is retained so the evaluation can answer "does symbolic retrieval actually
beat asking the model twice?" with a measurement rather than an assertion. The
live pipeline does not import this module; only scripts/evaluate.py does, and it
caches the score so the ablation never needs a second scoring run.
"""
import json
from typing import List

from app.core.logger import logger
from app.models.schemas import Argument, FactCheckResult
from app.services.grok_client import call_grok

_SYSTEM_PROMPT = (
    "You are a neutral fact-checker. You do not take a side in the debate. "
    "For each argument you are given, judge whether its core factual assertion "
    "is well supported by established knowledge. Respond ONLY with valid JSON, "
    "no prose wrapper, no markdown fences."
)


def _clean_json(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    elif cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    return cleaned.strip()


def _build_prompt(claim: str, arguments: List[Argument]) -> str:
    arg_lines = "\n".join(f'  "{a.id}": {json.dumps(a.text)}' for a in arguments)
    return f"""Claim under debate: {claim}

Arguments to fact-check (id -> text):
{{
{arg_lines}
}}

For every argument id above, return a JSON object of this exact shape:
{{
  "results": [
    {{
      "argument_id": "<id>",
      "support_score": 0.0,      // -1.0 = the assertion is contradicted by known facts,
                                 //  0.0 = mixed / not verifiable,
                                 // +1.0 = the assertion is well supported by known facts
      "reasoning": "one short sentence"
    }}
  ]
}}
Include exactly one entry per argument id. Return ONLY the JSON object."""


def _neutral_results(arguments: List[Argument]) -> List[FactCheckResult]:
    return [
        FactCheckResult(argument_id=a.id, evidence_sentences=[], support_score=0.0)
        for a in arguments
    ]


def check_transcript_llm(claim: str, arguments: List[Argument]) -> List[FactCheckResult]:
    """Fact-check every argument in the transcript with a single batched LLM call."""
    if not arguments:
        return []

    try:
        raw = call_grok(_build_prompt(claim, arguments), _SYSTEM_PROMPT)
        data = json.loads(_clean_json(raw))
        entries = data.get("results", []) if isinstance(data, dict) else []

        by_id = {}
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            arg_id = str(entry.get("argument_id", ""))
            try:
                score = float(entry.get("support_score", 0.0))
            except (TypeError, ValueError):
                score = 0.0
            score = max(-1.0, min(1.0, score))
            reasoning = str(entry.get("reasoning", "")).strip()
            by_id[arg_id] = (score, reasoning)

        results: List[FactCheckResult] = []
        for a in arguments:
            score, reasoning = by_id.get(a.id, (0.0, ""))
            results.append(
                FactCheckResult(
                    argument_id=a.id,
                    evidence_sentences=[reasoning] if reasoning else [],
                    support_score=score,
                )
            )
        return results
    except Exception as e:  # noqa: BLE001 - deliberate: never break the pipeline
        logger.warning(f"Fact-check failed, falling back to neutral scores: {e}")
        return _neutral_results(arguments)


def check_argument(argument_text: str) -> FactCheckResult:
    """Single-argument convenience wrapper around :func:`check_transcript_llm`."""
    stub = Argument(
        id="arg_1", agent="advocate", round=1, text=argument_text,
        attacks=[], self_confidence=0.5,
    )
    return check_transcript_llm(argument_text, [stub])[0]
