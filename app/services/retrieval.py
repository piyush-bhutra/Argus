"""PRD §5d - BM25 retrieval over the FEVER evidence corpus.

This is the only component that gives Argus information the debating model does
not already have. Everything symbolic downstream reasons over what this returns.

Offline and deterministic: no LLM, no network. The corpus is built by
scripts/prepare_fever.py.
"""
import json
import re
from functools import lru_cache
from pathlib import Path
from typing import List, Optional

from rank_bm25 import BM25Okapi

from app.core.logger import logger

_CORPUS_FILE = Path(__file__).resolve().parents[2] / "data" / "evidence_corpus.json"

_TOKEN = re.compile(r"[a-z0-9]+")


def tokenise(text) -> List[str]:
    """Lowercase alphanumeric tokens.

    No stopword list: BM25's IDF term already drives common words towards zero
    weight, and a hand-rolled stopword list is one more thing to get wrong.
    """
    if not text:
        return []
    return _TOKEN.findall(str(text).lower())


class Retriever:
    """BM25 index over evidence sentences."""

    def __init__(self, corpus: List[dict]):
        if not corpus:
            raise ValueError(
                "cannot build a retriever over an empty corpus - every query would "
                "return nothing and the symbolic fact-checker would abstain on "
                "every argument. Run: python -m scripts.prepare_fever"
            )
        self.corpus = list(corpus)
        self._bm25 = BM25Okapi([tokenise(row["text"]) for row in self.corpus])

    def retrieve(self, query: str, k: int = 5) -> List[dict]:
        """Top-k evidence sentences, each with its BM25 score, best first.

        Zero-scoring documents are dropped rather than padded out to k: a
        sentence sharing no terms with the argument is not weak evidence, it is
        no evidence, and passing it on would have the rule engine reason over
        text unrelated to the claim.
        """
        tokens = tokenise(query)
        if not tokens:
            return []

        scores = self._bm25.get_scores(tokens)
        ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:k]
        return [
            {**self.corpus[i], "score": float(scores[i])}
            for i in ranked
            if scores[i] > 0
        ]

    def recall_at_k(self, query: str, gold_ids: List[str], k: int = 5) -> Optional[float]:
        """Fraction of this claim's gold evidence that lands in the top k.

        Measures retrieval quality. Gold ids are never used to retrieve - that
        would be oracle retrieval. Returns None when there is no gold to score
        against, so callers can exclude rather than count it as a zero.
        """
        if not gold_ids:
            return None
        found = {h["id"] for h in self.retrieve(query, k)}
        return sum(1 for g in gold_ids if g in found) / len(gold_ids)


@lru_cache(maxsize=1)
def load_retriever(corpus_file: Optional[Path] = None) -> Optional[Retriever]:
    """Process-wide retriever over data/evidence_corpus.json, or None if absent.

    Returning None rather than raising keeps the live debate pipeline working on
    a checkout that has not run prepare_fever yet; the fact-checker then abstains
    and says so, instead of the API failing outright.
    """
    path = corpus_file or _CORPUS_FILE
    if not path.exists():
        logger.warning(
            f"No evidence corpus at {path} - retrieval disabled, the symbolic "
            f"fact-checker will abstain. Run: python -m scripts.prepare_fever"
        )
        return None
    try:
        return Retriever(json.loads(path.read_text(encoding="utf-8")))
    except (ValueError, OSError) as e:
        logger.warning(f"Could not load evidence corpus: {e}")
        return None
