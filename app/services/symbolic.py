"""PRD M4 - forward-chaining contradiction detection over a triple KB.

The division of labour that makes this worth doing: an LLM turns sentences into
triples (parsing, which it is good at), and this module decides what follows
(judging, which it is not). Nothing here calls a model, so the verdict it
produces is reproducible and every step of it can be shown to a reader.

It abstains rather than guesses. Strict triple matching has poor recall on
natural language, so an argument the rules cannot decide scores 0.0 with
`no_symbolic_match` and contributes nothing, rather than being assigned a
fabricated score. The abstention rate is reported as symbolic coverage, as a
metric rather than a footnote.
"""
import re
from typing import List, NamedTuple, Tuple

SUPPORT = 1.0
CONTRADICT = -1.0

# Predicates admitting exactly one object for a given subject. A mismatch here is
# a genuine conflict; for anything else (starred, mentions, located_near) two
# different objects are perfectly compatible. Curated deliberately: inferring
# functionality from data is a research problem of its own, and a wrong guess
# here manufactures false contradictions, which is the worst failure this module
# has. A predicate absent from this set never fires the functional rule.
FUNCTIONAL_PREDICATES = {
    "directed_by", "born_in", "born_on", "died_in", "died_on", "capital_of",
    "located_in", "height", "width", "length", "population", "released_in",
    "founded_in", "written_by", "produced_by", "nationality", "spouse_of",
    "country_of_origin", "tributary_of",
}

# The closed vocabulary the extractor is told to choose from. Argument triples
# and evidence triples only match when their predicates are identical after
# normalisation, and a free-form extractor names the same relation differently
# each time ("released_in" here, "release_date" there), so almost nothing
# matched: symbolic coverage measured 0.22 with 79 argument triples spread over
# dozens of ad-hoc predicates. Constraining the vocabulary makes both sides
# agree by construction.
CANONICAL_PREDICATES = [
    "is_a", "type", "genre", "part_of", "member_of", "includes",
    "directed_by", "written_by", "produced_by", "starring", "record_label",
    "born_in", "born_on", "died_in", "died_on", "nationality", "profession",
    "spouse_of", "sibling_of", "employer",
    "located_in", "capital_of", "country_of_origin", "tributary_of", "adjacent_to",
    "released_in", "founded_in", "height", "width", "length", "population",
    "language", "award", "role", "based_on",
]

# Drift the model produces anyway, folded onto the canonical name. Cheap
# insurance: a prompt constrains, it does not guarantee.
PREDICATE_ALIASES = {
    "release_date": "released_in", "released": "released_in", "release_year": "released_in",
    "year": "released_in", "premiered_in": "released_in",
    # NB: never alias a predicate that INVERSE_PREDICATES derives ("directed",
    # "wrote", "produced", "birthplace_of"), or the closure folds its own
    # derived facts back into the source predicate and chaining silently stops.
    "director": "directed_by", "writer": "written_by",
    "producer": "produced_by", "stars": "starring", "cast": "starring",
    "actor": "starring", "features": "starring",
    "birthplace": "born_in", "birth_date": "born_on", "birthdate": "born_on",
    "death_date": "died_on", "deathplace": "died_in",
    "occupation": "profession", "job": "profession", "works_as": "profession",
    "location": "located_in", "place": "located_in", "situated_in": "located_in",
    "country": "country_of_origin", "origin": "country_of_origin",
    "from": "country_of_origin", "nation": "nationality",
    "label": "record_label", "founded": "founded_in", "established_in": "founded_in",
    "kind": "type", "category": "genre", "belongs_to": "part_of",
    "married_to": "spouse_of",
}

# (film, directed_by, person) entails (person, directed, film). Deriving these
# is the forward-chaining step: it produces facts not literally present in the
# retrieved evidence.
INVERSE_PREDICATES = {
    "directed_by": "directed",
    "written_by": "wrote",
    "produced_by": "produced",
    "born_in": "birthplace_of",
}

# Canonical names only: "married_to" normalises to "spouse_of" via the alias
# map, so listing it here too would be dead weight.
SYMMETRIC_PREDICATES = {"spouse_of", "sibling_of", "adjacent_to"}

_ARTICLES = {"the", "a", "an"}
_NUMBER = re.compile(r"-?\d+(?:[.,]\d+)?")
_MAX_CLOSURE_PASSES = 10


class Triple(NamedTuple):
    subject: str
    predicate: str
    object: str
    negated: bool = False
    source: str = ""     # evidence id, or argument id


def normalise_entity(text) -> str:
    """Surface form -> comparison key. Lowercase, de-articled, depunctuated."""
    if not text:
        return ""
    cleaned = re.sub(r"[^\w\s]", " ", str(text).lower())
    words = [w for w in cleaned.split() if w]
    while words and words[0] in _ARTICLES:
        words.pop(0)
    return " ".join(words)


def normalise_predicate(text) -> str:
    """Predicate surface form -> canonical name, folding known aliases.

    Both sides of a match go through this, so "release_date" on the evidence
    side and "released_in" on the argument side become the same predicate.
    """
    key = normalise_entity(text).replace(" ", "_")
    return PREDICATE_ALIASES.get(key, key)


def _key(triple: Triple) -> tuple:
    return (
        normalise_entity(triple.subject),
        normalise_predicate(triple.predicate),
        normalise_entity(triple.object),
        triple.negated,
    )


def canonical(triple: Triple) -> Triple:
    """Triple with subject/predicate/object in normalised form.

    The KB is stored canonical so scoring compares keys directly instead of
    re-normalising every fact on every lookup. Surface forms are not lost: the
    `source` id still points at the evidence sentence, which is what gets shown
    to a reader.
    """
    return triple._replace(
        subject=normalise_entity(triple.subject),
        predicate=normalise_predicate(triple.predicate),
        object=normalise_entity(triple.object),
    )


def derive_closure(triples: List[Triple]) -> List[Triple]:
    """Forward-chain the inverse and symmetric rules to a fixpoint.

    Returns canonical triples. Deduplicated on the normalised key, which is what
    makes termination guaranteed: symmetric predicates would otherwise regenerate
    each other forever. The pass cap is a belt-and-braces guard against a future
    rule that can grow the KB without bound.
    """
    seen = {}
    for t in triples:
        c = canonical(t)
        seen.setdefault(_key(c), c)

    for _ in range(_MAX_CLOSURE_PASSES):
        added = False
        for t in list(seen.values()):
            pred = normalise_predicate(t.predicate)
            derived = []

            inverse = INVERSE_PREDICATES.get(pred)
            if inverse:
                derived.append(t._replace(subject=t.object, predicate=inverse, object=t.subject))
            if pred in SYMMETRIC_PREDICATES:
                derived.append(t._replace(subject=t.object, object=t.subject))

            for d in (canonical(x) for x in derived):
                if _key(d) not in seen:
                    # Provenance rides along: a derived fact is still traceable to
                    # the evidence sentence it came from.
                    seen[_key(d)] = d
                    added = True
        if not added:
            break

    return list(seen.values())


def _numbers(text: str) -> List[float]:
    return [float(m.replace(",", "")) for m in _NUMBER.findall(str(text))]


def _objects_agree(a: str, b: str) -> bool:
    """Do two object surface forms denote the same value?

    Numbers are compared as numbers when both sides carry them, so "319 metres"
    and "319 m" agree while "319 metres" and "443 metres" do not. Otherwise one
    string containing the other counts as agreement, which absorbs the common
    "New York" / "New York City" style of variation.
    """
    na, nb = normalise_entity(a), normalise_entity(b)
    if not na or not nb:
        return False

    nums_a, nums_b = _numbers(na), _numbers(nb)
    if nums_a and nums_b:
        return nums_a[0] == nums_b[0]

    return na == nb or na in nb or nb in na


def score_triple(triple: Triple, kb: List[Triple]) -> Tuple[float, str, List[str]]:
    """Score one argument triple against the KB.

    Returns (score in [-1,1], rule name, evidence ids that fired).

    Contradiction takes precedence over support: when the KB holds conflicting
    facts about the same subject and predicate, reporting support would hide a
    conflict the reader should see.
    """
    if not (normalise_entity(triple.subject)
            and normalise_predicate(triple.predicate)
            and normalise_entity(triple.object)):
        return 0.0, "no_symbolic_match", []

    subj = normalise_entity(triple.subject)
    pred = normalise_predicate(triple.predicate)
    is_functional = pred in FUNCTIONAL_PREDICATES

    supports, contradictions = [], []

    for fact in kb:
        # kb is canonical (derive_closure), so these compare directly.
        if fact.subject != subj or fact.predicate != pred:
            continue

        agree = _objects_agree(triple.object, fact.object)

        if agree and fact.negated != triple.negated:
            contradictions.append(("negation", fact.source))
        elif agree:
            supports.append(fact.source)
        elif is_functional and fact.negated == triple.negated:
            nums_t, nums_f = _numbers(triple.object), _numbers(fact.object)
            rule = "numeric_mismatch" if (nums_t and nums_f) else "functional_contradiction"
            contradictions.append((rule, fact.source))

    if contradictions:
        rule = contradictions[0][0]
        return CONTRADICT, rule, [s for _, s in contradictions if s]
    if supports:
        return SUPPORT, "entailment", [s for s in supports if s]
    return 0.0, "no_symbolic_match", []
