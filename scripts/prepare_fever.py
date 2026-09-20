"""
Build a small, balanced, held-out FEVER sample for calibration training/eval.

    python -m scripts.prepare_fever --n 50 --seed 42

Writes data/fever_sample.json as [{"claim": str, "label": bool}] where
label=True means SUPPORTED. NOTENOUGHINFO claims are dropped — the system
outputs a single P(true), so a three-way label has nowhere to go.

Offline/eval data only. Nothing in app/ reads this file; the live debate
pipeline is untouched.
"""
import argparse
import hashlib
import json
import random
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "data" / "fever_sample.json"
DEFAULT_CORPUS = ROOT / "data" / "evidence_corpus.json"

# FEVER stores Wikipedia text with the brackets escaped and page titles
# underscored. BM25 tokenises on words, so "-LRB-" would otherwise become a
# high-frequency junk token appearing in a large share of the corpus.
_MARKUP = {
    "-LRB-": "(", "-RRB-": ")",
    "-LSB-": "[", "-RSB-": "]",
    "-COLON-": ":",
}

# Tried in order. The canonical `fever` repo is script-based and no longer
# loadable by datasets>=4, so the mirror is what actually serves us today —
# it's kept first anyway in case the hub restores a parquet export.
SOURCES = [
    ("fever", "v1.0", "labelled_dev"),
    ("copenlu/fever_gold_evidence", None, "validation"),
    ("copenlu/fever_gold_evidence", None, "test"),
]

# Only explicit textual labels. Integer label columns on FEVER-adjacent
# datasets mean different things per dataset (e.g. evidence relatedness) —
# mapping them blind silently produces mislabelled data.
SUPPORTED = {"SUPPORTS", "SUPPORTED", "TRUE"}
REFUTED = {"REFUTES", "REFUTED", "FALSE"}

# Fallback if every public path fails. Hand-written, deliberately mixed
# difficulty, balanced 10/10.
FALLBACK = [
    ("The Eiffel Tower is located in Paris, France.", True),
    ("Water boils at 100 degrees Celsius at sea-level atmospheric pressure.", True),
    ("The human heart has four chambers.", True),
    ("Mount Everest is the highest mountain above sea level on Earth.", True),
    ("Python was first released in 1991.", True),
    ("The Pacific Ocean is the largest ocean on Earth.", True),
    ("Insulin is produced in the pancreas.", True),
    ("The Berlin Wall fell in 1989.", True),
    ("DNA is structured as a double helix.", True),
    ("Brazil is the largest country in South America by area.", True),
    ("The Great Wall of China is visible from the Moon with the naked eye.", False),
    ("Humans use only ten percent of their brains.", False),
    ("Sydney is the capital city of Australia.", False),
    ("The Sun orbits the Earth once per year.", False),
    ("Antibiotics are an effective treatment for viral influenza.", False),
    ("Goldfish have a memory span of only three seconds.", False),
    ("Lightning never strikes the same place twice.", False),
    ("The Amazon rainforest produces twenty percent of the world's oxygen.", False),
    ("Napoleon Bonaparte was unusually short for his era.", False),
    ("Bats are blind.", False),
]


def normalise_fever_text(text) -> str:
    """FEVER wiki markup -> plain text. Safe to apply twice."""
    if not text:
        return ""
    out = str(text)
    for token, char in _MARKUP.items():
        out = out.replace(token, char)
    out = out.replace("_", " ")
    return re.sub(r"\s+", " ", out).strip()


def evidence_id(page, sent_id) -> str:
    """Stable id for one Wikipedia sentence.

    Hashed rather than f"{page}:{sent_id}" so the id is a fixed-width token that
    survives being used as a dict key, a filename fragment and a JSON field
    without escaping concerns - page titles contain slashes, quotes and colons.
    """
    key = f"{normalise_fever_text(page)}|{sent_id}"
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]


def build_corpus(evidence_by_claim: dict):
    """claim -> raw FEVER evidence  ==>  (corpus rows, claim -> gold evidence ids).

    The corpus is the deduplicated union of every sentence supplied, pooled across
    ALL claims loaded - not just the ones being scored. That is deliberate: a
    corpus containing only the scored claims' own evidence makes retrieval
    trivially easy and the evaluation optimistic.

    The gold id map exists to MEASURE retrieval (recall@k). It is never given to
    the retriever, which would be oracle retrieval.
    """
    corpus: dict[str, dict] = {}
    gold: dict[str, list[str]] = {}

    for claim, evidences in evidence_by_claim.items():
        ids = []
        for ev in evidences or []:
            # Rows are [page_title, sentence_id, sentence_text]; anything else is
            # a schema variant we do not understand and must not guess at.
            if not isinstance(ev, (list, tuple)) or len(ev) < 3:
                continue
            page, sent_id, text = ev[0], ev[1], ev[2]
            clean = normalise_fever_text(text)
            if not clean:
                continue
            eid = evidence_id(page, sent_id)
            corpus.setdefault(eid, {
                "id": eid,
                "page": normalise_fever_text(page),
                "sent_id": str(sent_id),
                "text": clean,
            })
            if eid not in ids:
                ids.append(eid)
        gold[claim] = ids

    if not corpus:
        raise ValueError(
            "no usable evidence found - refusing to write an empty corpus. "
            "Retrieval would return nothing and the symbolic fact-checker would "
            "abstain on every argument, which fails silently rather than loudly."
        )

    return sorted(corpus.values(), key=lambda r: r["id"]), gold


def _label(row):
    """Row -> True/False/None, tolerating the various FEVER schema variants."""
    raw = row.get("label", row.get("labels", row.get("gold_label")))
    if raw is None:
        return None
    key = str(raw).strip().upper()
    if key in SUPPORTED:
        return True
    if key in REFUTED:
        return False
    return None


def load_fever():
    """First public source that loads wins.

    Returns (rows, evidence_by_claim, source_name). ``evidence_by_claim`` holds the
    raw evidence for EVERY loaded claim, not just the sampled ones - the corpus is
    pooled across all of them so retrieval faces realistic distractors.
    """
    from datasets import load_dataset

    errors = []
    for path, config, split in SOURCES:
        name = f"{path}" + (f":{config}" if config else "") + f"/{split}"
        try:
            ds = load_dataset(path, config, split=split) if config else load_dataset(path, split=split)
            rows, evidence = [], {}
            for r in ds:
                claim = r.get("claim")
                label = _label(r) if claim else None
                if not claim or label is None:
                    continue
                rows.append((claim, label))
                # A claim repeated with a second evidence set contributes both.
                evidence.setdefault(claim, []).extend(r.get("evidence") or [])
            # A source that yields nothing usable (wrong label semantics, wrong
            # schema) falls through to the next rather than writing junk.
            if rows:
                return rows, evidence, name
            errors.append(f"{name}: loaded but no usable SUPPORTED/REFUTED rows")
        except Exception as exc:  # noqa: BLE001 - any failure just means "try the next one"
            errors.append(f"{name}: {type(exc).__name__}: {exc}")
    print("All public FEVER sources failed:")
    for e in errors:
        print("  -", e)
    return None, None, None


def balance(rows, n, rng):
    """Class-balanced sample of (claim, label) pairs: n//2 of each class.

    If either class has fewer than n//2 claims, BOTH are capped at the smaller
    count - the split stays exactly even rather than being padded. An odd n
    rounds down (n=51 -> 25/25).

    Claims are de-duplicated first (FEVER repeats a claim once per evidence
    set); a claim seen with both labels is dropped as ambiguous. Duplicates
    would otherwise collide in the eval cache, which is keyed by claim text.
    """
    labels_by_claim = {}
    for claim, label in rows:
        labels_by_claim.setdefault(claim, set()).add(label)
    unique = sorted((c, next(iter(ls))) for c, ls in labels_by_claim.items() if len(ls) == 1)

    pos = [r for r in unique if r[1]]
    neg = [r for r in unique if not r[1]]
    per = min(n // 2, len(pos), len(neg))
    out = rng.sample(pos, per) + rng.sample(neg, per)
    rng.shuffle(out)
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--n", "--size", dest="n", type=int, default=50,
                   help="total claims, split 50/50 SUPPORTED/REFUTED (default 50)")
    p.add_argument("--seed", type=int, default=42, help="random seed (default 42)")
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    p.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS,
                   help="where to write the pooled BM25 evidence corpus")
    p.add_argument("--exclude", type=Path, action="append", default=[],
                   help="a sample file whose claims must NOT appear here; repeatable")
    args = p.parse_args()

    rng = random.Random(args.seed)

    # Claims already spent as evaluation data. Fitting the calibrator on a claim
    # that is also scored in the held-out set is the single mistake that would
    # invalidate every number in the write-up, so it is made impossible here
    # rather than avoided by discipline.
    excluded = set()
    for f in args.exclude:
        if not f.exists():
            raise SystemExit(f"--exclude file not found: {f}")
        excluded.update(r["claim"] for r in json.loads(f.read_text(encoding="utf-8")))

    rows, evidence_by_claim, source = load_fever()
    if rows is None:
        rows, evidence_by_claim = FALLBACK, {}
        source = "built-in fallback claim set (no download)"

    if excluded:
        before = len(rows)
        rows = [(c, lb) for c, lb in rows if c not in excluded]
        print(f"excluded {before - len(rows)} row(s) matching {len(excluded)} held-out claim(s)")

    sample = balance(rows, args.n, rng)
    overlap = {c for c, _ in sample} & excluded
    assert not overlap, f"REFUSING to write: {len(overlap)} claim(s) overlap the excluded set"
    n_true = sum(1 for _, lb in sample if lb)
    n_false = len(sample) - n_true
    assert n_true == n_false, f"balance() produced {n_true}/{n_false} - refusing to write"

    # Corpus is pooled over EVERY loaded claim, not just the sampled ones, so a
    # sampled claim's evidence sits among realistic distractors rather than in a
    # corpus consisting only of answers.
    corpus, gold = [], {}
    if evidence_by_claim:
        corpus, gold = build_corpus(evidence_by_claim)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(
            [{"claim": c, "label": lb, "evidence_ids": gold.get(c, [])} for c, lb in sample],
            indent=2,
        ),
        encoding="utf-8",
    )
    if corpus:
        args.corpus.write_text(json.dumps(corpus, indent=2), encoding="utf-8")

    print(f"source: {source}")
    print(f"seed:   {args.seed}")
    print("=" * 50)
    print(f"CLASS COUNTS: {n_true} true (SUPPORTED) / {n_false} false (REFUTED), n={len(sample)}")
    print("=" * 50)
    if corpus:
        covered = sum(1 for c, _ in sample if gold.get(c))
        print(f"corpus:  {len(corpus)} sentences pooled from {len(evidence_by_claim)} claims")
        print(f"         {covered}/{len(sample)} sampled claims have gold evidence in it")
        print(f"wrote {args.corpus}")
    else:
        print("WARNING: no evidence available from this source, so NO corpus was "
              "written. BM25 retrieval and the symbolic fact-checker cannot run "
              "without one.")
    if len(sample) < args.n:
        print(f"WARNING: requested n={args.n}, got {len(sample)} - "
              f"{'odd n rounds down' if len(sample) == args.n - 1 else 'a class ran short; both capped to match'}")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
