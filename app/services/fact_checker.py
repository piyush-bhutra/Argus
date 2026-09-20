"""PRD §5d - Fact-Checking / KB Chaining Module.

    retrieve evidence (BM25)  ->  LLM extracts triples  ->  symbolic rules judge

The LLM's role here is parsing only: it turns sentences into
(subject, predicate, object) triples. It is never asked whether an argument is
true. That matters because the same model generated the arguments, so asking it
to grade them supplies no information the debate did not already contain — which
is precisely why the previous version of this module added nothing.

The verdict comes from app/services/symbolic.py, which reasons over triples
extracted from RETRIEVED EVIDENCE. That evidence is the only thing in Argus the
single-call baseline does not have.

Degrades to neutral (0.0) on any failure, and abstains rather than guessing when
the rules cannot decide. The abstention rate is reported as symbolic coverage.
"""
import json
from typing import List, Optional

from app.core.logger import logger
from app.models.schemas import Argument, FactCheckResult
from app.services.grok_client import call_grok
from app.services.retrieval import load_retriever
from app.services.symbolic import (
    CANONICAL_PREDICATES, Triple, derive_closure, score_triple,
)

DEFAULT_K = 5

_SYSTEM_PROMPT = (
    "You extract structured facts from text. You do not evaluate, rate, or judge "
    "anything — you only convert each sentence into (subject, predicate, object) "
    "triples. Set negated to true when the sentence denies the relation. Respond "
    "ONLY with valid JSON, no prose wrapper, no markdown fences."
)

# The predicate vocabulary goes in the USER prompt, next to the texts, because a
# free-form extractor names the same relation differently in different calls and
# the rules can only match identical predicates.
_PREDICATE_INSTRUCTION = (
    "Prefer these predicates wherever one fits:\n  "
    + ", ".join(CANONICAL_PREDICATES)
    + "\n\nIf none fits, use your own short snake_case predicate — do not skip "
      "the fact. Extract every factual relation you can. Write subjects and "
      "objects as the specific named entity, not a pronoun or a generic noun "
      "('Jackie', not 'the film'; 'Pablo Larrain', not 'the director')."
)
# Measured, not assumed: an earlier version said "use ONLY these" and "omit the
# fact rather than invent a predicate". Triple yield fell from 1.55 per argument
# to 0.52, arguments yielding nothing rose from 25% to 69%, and symbolic coverage
# collapsed from 0.22 to 0.04. Consistency pressure is worth having; refusing
# facts that fall outside the list is not.


def _clean_json(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    elif cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    return cleaned.strip()


def _build_prompt(items: List[tuple]) -> str:
    lines = "\n".join(f'  {{"id": "{sid}", "text": {json.dumps(text)}}},' for sid, text in items)
    return f"""Extract factual triples from each numbered text below.

{_PREDICATE_INSTRUCTION}

Texts:
[
{lines}
]

Return exactly this JSON shape:
{{
  "triples": [
    {{"source_id": "<the id of the text it came from>",
      "subject": "...", "predicate": "...", "object": "...", "negated": false}}
  ]
}}

Emit one entry per distinct fact. A text may yield several triples, or none if it
states no factual relation. Return ONLY the JSON object."""


def _parse_triples(raw: str) -> dict:
    """LLM response -> {source_id: [Triple, ...]}. Never raises."""
    by_source: dict = {}
    try:
        data = json.loads(_clean_json(raw))
        entries = data.get("triples", []) if isinstance(data, dict) else []
    except (ValueError, AttributeError) as e:
        logger.warning(f"fact_checker: could not parse triple extraction: {e}")
        return by_source

    for e in entries:
        if not isinstance(e, dict):
            continue
        sid = str(e.get("source_id", "")).strip()
        subject = str(e.get("subject", "") or "").strip()
        predicate = str(e.get("predicate", "") or "").strip()
        obj = str(e.get("object", "") or "").strip()
        if not (sid and subject and predicate and obj):
            continue
        by_source.setdefault(sid, []).append(
            Triple(
                subject=subject,
                predicate=predicate,
                object=obj,
                negated=bool(e.get("negated", False)),
                source=sid,
            )
        )
    return by_source


def _neutral(argument: Argument, evidence=(), triples=()) -> FactCheckResult:
    return FactCheckResult(
        argument_id=argument.id,
        evidence_sentences=[e["text"] for e in evidence],
        support_score=0.0,
        method="none",
        rules_fired=[],
        evidence_ids=[e["id"] for e in evidence],
        triples=list(triples),
    )


def check_transcript(
    claim: str,
    arguments: List[Argument],
    retriever=None,
    k: int = DEFAULT_K,
) -> List[FactCheckResult]:
    """Score every argument against retrieved evidence. One LLM call total."""
    if not arguments:
        return []

    if retriever is None:
        retriever = load_retriever()
    if retriever is None:
        # No corpus means nothing to reason over. Abstaining is the honest
        # outcome; falling back to asking the model would reintroduce the
        # circularity this module exists to remove.
        logger.warning("fact_checker: no evidence corpus, abstaining on every argument")
        return [_neutral(a) for a in arguments]

    # Retrieve on the CLAIM as well as per argument, and pool everything into one
    # KB for the debate.
    #
    # Querying with "claim + argument text" alone was a bug: an argument's prose
    # dominates BM25 and pulls evidence about whatever entities it mentions in
    # passing. On "The Columbia River undergoes drainage" that retrieved British
    # Columbia, the Tualatin River and the River Mersey, sharing not one subject
    # with the argument's own triples — so the rules had nothing to match and
    # abstained. It also meant the measured recall@5 of 0.836, taken on the claim
    # alone, did not describe the query actually being issued.
    claim_evidence = retriever.retrieve(claim, k=k)
    evidence_by_arg = {a.id: retriever.retrieve(f"{claim} {a.text}", k=k) for a in arguments}

    unique_evidence = {e["id"]: e for e in claim_evidence}
    for hits in evidence_by_arg.values():
        for e in hits:
            unique_evidence.setdefault(e["id"], e)

    items = [(a.id, a.text) for a in arguments]
    items += [(eid, e["text"]) for eid, e in unique_evidence.items()]

    try:
        raw = call_grok(_build_prompt(items), _SYSTEM_PROMPT)
    except Exception as e:  # noqa: BLE001 - a provider failure must not kill the debate
        logger.warning(f"fact_checker: extraction call failed ({e}); abstaining")
        return [_neutral(a, evidence_by_arg[a.id]) for a in arguments]

    triples_by_source = _parse_triples(raw)

    # One KB for the whole debate, over every retrieved sentence. Scoping the KB
    # to each argument's own hits starved arguments whose retrieval went astray,
    # even when the claim's evidence had been fetched for a sibling argument.
    kb = derive_closure([t for eid in unique_evidence for t in triples_by_source.get(eid, [])])

    results = []
    for a in arguments:
        # Provenance still shows this argument's own hits; the KB is shared.
        evidence = evidence_by_arg[a.id] or claim_evidence

        arg_triples = triples_by_source.get(a.id, [])
        scores, rules, sources = [], [], []
        for t in arg_triples:
            score, rule, fired = score_triple(t, kb)
            if rule == "no_symbolic_match":
                continue
            scores.append(score)
            rules.append(rule)
            sources.extend(fired)

        shown = [f"{t.subject} | {t.predicate} | {t.object}" for t in arg_triples]

        if not scores:
            results.append(_neutral(a, evidence, shown))
            continue

        # The sentences that actually FIRED a rule, not merely the top-k that
        # were retrieved. Showing retrieved-but-unused evidence beside a score
        # makes the trace misleading: a real debate rendered a contradiction
        # against a sentence about journalism that had nothing to do with it.
        fired_texts = [
            unique_evidence[eid]["text"]
            for eid in sorted(set(sources))
            if eid in unique_evidence
        ]

        results.append(
            FactCheckResult(
                argument_id=a.id,
                evidence_sentences=fired_texts or [e["text"] for e in evidence],
                support_score=sum(scores) / len(scores),
                method="symbolic",
                rules_fired=rules,
                # Only the evidence that actually fired a rule, not everything
                # retrieved — this is the audit trail for THIS score.
                evidence_ids=sorted(set(sources)),
                triples=shown,
            )
        )
    return results


def symbolic_coverage(results: List[FactCheckResult]) -> Optional[float]:
    """Fraction of arguments the rules could decide.

    Reported as a first-class metric: strict triple matching has poor recall on
    natural language, and an honest coverage number is a result, while a hidden
    one is a gimmick.
    """
    if not results:
        return None
    return sum(1 for r in results if r.method == "symbolic") / len(results)
