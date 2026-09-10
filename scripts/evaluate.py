"""
Offline evaluation harness: Argus (full debate pipeline) vs a single-LLM baseline,
scored against the FEVER sample from scripts/prepare_fever.py.

    python -m scripts.evaluate --limit 10          # small smoke run first
    python -m scripts.evaluate                     # full sample

Reports accuracy (threshold 0.5) and Expected Calibration Error for both systems.
Writes data/eval_results.json (per claim, incrementally) and data/eval_summary.json.

Results are cached per claim AND per half (Argus / baseline), each half stamped
with the config that produced it. Re-running skips any half whose stamp matches
the current config, so a run killed by the daily LLM quota resumes where it
stopped, and a config change re-scores only the half it affects. Use --refresh
to redo everything.

This harness only CALLS app/services - it changes nothing in the live pipeline.
"""
import argparse
import hashlib
import json
import math
import os
import time
import random
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import settings
from app.services import grok_client
from app.services.grok_client import call_grok, _is_daily_quota_exhausted
from app.services.judge import apply_calibration
from app.services.orchestrator import run_debate
from app.services.pipeline import _load_calibrator, assemble_verdict
from scripts.prepare_fever import balance

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "data" / "fever_sample.json"
RESULTS = ROOT / "data" / "eval_results.json"
SUMMARY = ROOT / "data" / "eval_summary.json"

_BASELINE_SYSTEM = (
    "You are a fact-verification system. Given a claim, judge how likely it is to "
    "be true. Respond with ONLY a single number between 0 and 1 - no prose, no "
    "explanation, no markdown. 1 means certainly true, 0 means certainly false."
)


# --- metrics ---------------------------------------------------------------
# Shared with scripts/reliability_diagram.py - keep the binning in one place.

def accuracy(probs, labels, threshold=0.5):
    if not probs:
        return None
    hits = sum((p >= threshold) == lb for p, lb in zip(probs, labels))
    return hits / len(probs)


def bin_stats(probs, labels, bins=10):
    """Equal-width bins over [0,1] -> list of {lo, hi, count, confidence, accuracy}.

    Bin i covers [i/bins, (i+1)/bins); p == 1.0 falls in the last bin.
    """
    out = []
    for i in range(bins):
        lo, hi = i / bins, (i + 1) / bins
        members = [
            (p, lb)
            for p, lb in zip(probs, labels)
            if (lo <= p < hi) or (i == bins - 1 and p == 1.0)
        ]
        out.append(
            {
                "lo": lo,
                "hi": hi,
                "count": len(members),
                "confidence": sum(p for p, _ in members) / len(members) if members else None,
                "accuracy": sum(1 for _, lb in members if lb) / len(members) if members else None,
            }
        )
    return out


def ece(probs, labels, bins=10):
    """Expected Calibration Error: sum over bins of (n_bin/N) * |acc - conf|.

    This is the standard confidence-vs-frequency ECE for a probability of the
    positive class: within a bin, mean predicted P(true) is compared against the
    observed fraction of genuinely true claims.
    """
    if not probs:
        return None
    n = len(probs)
    return sum(
        (b["count"] / n) * abs(b["accuracy"] - b["confidence"])
        for b in bin_stats(probs, labels, bins)
        if b["count"]
    )


# --- systems under test ----------------------------------------------------

def run_argus(claim: str, rounds: int) -> dict:
    """Debate + semantics + fact-check + judge. Returns the RAW probability;
    calibration is applied at read time (see apply_current_calibrator) so a
    newly trained calibrator never forces the debates to be re-run."""
    transcript = run_debate(claim, rounds)
    verdict = assemble_verdict(claim, transcript, calibrator=None)
    return {
        "raw_probability": verdict.raw_probability,
        "n_arguments": len(transcript),
        "grounded_extension": verdict.grounded_extension,
    }


def run_baseline(claim: str) -> float:
    """One direct LLM call: 'how likely is this claim true?' -> float in [0,1]."""
    text = call_grok(f"Claim: {claim}\n\nProbability the claim is true:", _BASELINE_SYSTEM)
    cleaned = text.strip().strip("`").split()[0].rstrip(".,")
    return min(1.0, max(0.0, float(cleaned)))


# --- cache -----------------------------------------------------------------
# An entry is uniquely identified by (claim text, half, that half's key). The
# key holds every setting that changes the half's score:
#   argus:    rounds, llm_model, llm_base_url
#   baseline: llm_model, llm_base_url, sha256 of the baseline prompt
# The calibrator is deliberately NOT in the Argus key: the raw probability is
# cached and calibrated at read time. The ground-truth label is never trusted
# from the cache - it is always re-read from the sample file.

def argus_key(rounds: int) -> dict:
    return {"rounds": rounds, "llm_model": settings.llm_model,
            "llm_base_url": settings.llm_base_url}


def baseline_key() -> dict:
    return {"llm_model": settings.llm_model, "llm_base_url": settings.llm_base_url,
            "prompt_sha256": hashlib.sha256(_BASELINE_SYSTEM.encode()).hexdigest()[:16]}


def _is_prob(x) -> bool:
    return (isinstance(x, (int, float)) and not isinstance(x, bool)
            and math.isfinite(x) and 0.0 <= x <= 1.0)


def half_is_cached(row: dict, prob_field: str, key_field: str, key: dict) -> bool:
    """A half counts as done only if its score is a valid probability AND it was
    produced under the current config. Anything else is recomputed."""
    return _is_prob(row.get(prob_field)) and row.get(key_field) == key


def load_cache() -> dict:
    """claim -> row. Fails safe: a file that won't parse is moved aside (never
    deleted) and the run starts clean; individual malformed rows are dropped
    so just those claims get re-scored."""
    if not RESULTS.exists():
        return {}
    try:
        rows = json.loads(RESULTS.read_text(encoding="utf-8"))
        if not isinstance(rows, list):
            raise ValueError(f"expected a JSON list, got {type(rows).__name__}")
    except (ValueError, UnicodeDecodeError) as exc:
        backup = RESULTS.with_name(
            f"{RESULTS.stem}.corrupt-{datetime.now():%Y%m%d-%H%M%S}{RESULTS.suffix}")
        RESULTS.replace(backup)
        print(f"WARNING: {RESULTS.name} is unreadable ({exc}); moved to {backup.name}, "
              f"starting with an empty cache.")
        return {}

    cache, dropped = {}, 0
    for row in rows:
        if isinstance(row, dict) and isinstance(row.get("claim"), str):
            cache[row["claim"]] = row
        else:
            dropped += 1
    if dropped:
        print(f"WARNING: dropped {dropped} malformed cache row(s); they will be re-scored.")
    return cache


def save_cache(cache: dict) -> None:
    """Atomic write: a crash mid-save leaves the previous file intact, never a
    half-written one."""
    tmp = RESULTS.with_name(RESULTS.name + ".tmp")
    tmp.write_text(json.dumps(list(cache.values()), indent=2), encoding="utf-8")
    os.replace(tmp, RESULTS)


def apply_current_calibrator(row: dict, calibrator) -> None:
    raw = row.get("argus_raw_probability")
    if not _is_prob(raw):
        row["argus_probability"] = None
    else:
        row["argus_probability"] = (
            apply_calibration(calibrator, raw) if calibrator is not None else raw)


# --- harness ---------------------------------------------------------------

def summarise(rows, bins, config) -> dict:
    def side(key):
        pairs = [(r[key], r["label"]) for r in rows if r.get(key) is not None]
        probs = [p for p, _ in pairs]
        labels = [lb for _, lb in pairs]
        return {
            "n": len(probs),
            "n_true": sum(labels),
            "n_false": len(labels) - sum(labels),
            "accuracy": accuracy(probs, labels),
            "ece": ece(probs, labels, bins),
            "mean_probability": sum(probs) / len(probs) if probs else None,
            "bins": bin_stats(probs, labels, bins),
        }

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "config": config,
        "n_claims_scored": len(rows),
        "n_claims_failed": sum(1 for r in rows if r.get("error")),
        "argus": side("argus_probability"),
        "baseline": side("baseline_probability"),
        # Exactly the scores the metrics above were computed from. The results
        # file is a multi-config cache; this is the per-run record, and what
        # scripts/reliability_diagram.py plots.
        "claims": [
            {k: r.get(k) for k in ("claim", "label", "argus_probability", "baseline_probability")}
            for r in rows
        ],
    }


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--limit", type=int,
                   help="score only N claims, drawn class-balanced by --seed")
    p.add_argument("--seed", type=int, default=42, help="seed for subset selection (default 42)")
    p.add_argument("--rounds", type=int, default=2, help="debate rounds per claim (default 2)")
    p.add_argument("--bins", type=int, default=10, help="ECE bins (default 10)")
    p.add_argument("--delay", type=float, default=5.0,
                   help="seconds to sleep between claims, for rate limits (default 5)")
    p.add_argument("--refresh", action="store_true", help="ignore the cache and rescore everything")
    p.add_argument("--no-baseline", action="store_true", help="skip the single-LLM baseline")
    p.add_argument("--llm-timeout", type=float, default=180.0,
                   help="per-call LLM timeout in seconds for this run only (default 180)")
    args = p.parse_args(argv)

    # ponytail: harness-local override of the client's 60s request timeout. A
    # batch run tolerates a slow provider far better than an interactive debate
    # does, so it is raised here rather than in grok_client - the live pipeline's
    # behaviour is deliberately left untouched. Must precede the first call, as
    # the client is built lazily and then cached.
    grok_client._REQUEST_TIMEOUT = args.llm_timeout

    if not SAMPLE.exists():
        raise SystemExit(f"{SAMPLE} not found - run: python -m scripts.prepare_fever")

    claims = json.loads(SAMPLE.read_text(encoding="utf-8"))
    if args.limit and args.limit < len(claims):
        # Stratified, not a plain random.sample: an unbalanced subset lets an
        # "always false" system score well for free.
        subset = balance([(r["claim"], r["label"]) for r in claims],
                         args.limit, random.Random(args.seed))
        claims = [{"claim": c, "label": lb} for c, lb in subset]

    cache = {} if args.refresh else load_cache()
    calibrator = _load_calibrator()
    a_key, b_key = argus_key(args.rounds), baseline_key()
    n_true = sum(1 for r in claims if r["label"])
    config = {
        "sample_file": str(SAMPLE.relative_to(ROOT)),
        "n_claims_requested": len(claims),
        "n_true": n_true,
        "n_false": len(claims) - n_true,
        "rounds": args.rounds,
        "bins": args.bins,
        "seed": args.seed,
        "limit": args.limit,
        "llm_model": settings.llm_model,
        "llm_base_url": settings.llm_base_url,
        "calibrator_loaded": calibrator is not None,
        "baseline_enabled": not args.no_baseline,
        "argus_key": a_key,
        "baseline_key": b_key,
    }
    print(json.dumps(config, indent=2))
    print(f"\nCLASS COUNTS: {n_true} true / {len(claims) - n_true} false, n={len(claims)}")
    if calibrator is None:
        print("No trained calibrator - Argus calibrated == raw for this run.\n")

    aborted = None
    for i, row in enumerate(claims, 1):
        claim, label = row["claim"], row["label"]
        result = cache.get(claim) or {"claim": claim}
        result["label"] = label  # ground truth always comes from the sample
        need_argus = not half_is_cached(result, "argus_raw_probability", "argus_key", a_key)
        need_baseline = not args.no_baseline and not half_is_cached(
            result, "baseline_probability", "baseline_key", b_key)
        if not need_argus and not need_baseline:
            print(f"[{i}/{len(claims)}] cached: {claim[:70]}")
            cache[claim] = result
            continue

        print(f"[{i}/{len(claims)}] {claim[:70]}")
        result.pop("error", None)
        try:
            if need_argus:
                argus = run_argus(claim, args.rounds)
                result["argus_raw_probability"] = argus["raw_probability"]
                result["n_arguments"] = argus["n_arguments"]
                result["grounded_extension"] = argus["grounded_extension"]
                result["argus_key"] = a_key

            if need_baseline:
                result["baseline_probability"] = run_baseline(claim)
                result["baseline_key"] = b_key

            apply_current_calibrator(result, calibrator)
            print(f"    label={label}  argus={result['argus_probability']:.2f}  "
                  f"baseline={result.get('baseline_probability')}")
        except Exception as exc:  # noqa: BLE001
            result["error"] = f"{type(exc).__name__}: {exc}"[:300]
            print(f"    FAILED: {result['error']}")
            # A per-day quota won't recover in this run; stop and keep what we have.
            if _is_daily_quota_exhausted(exc):
                cache[claim] = result
                save_cache(cache)
                aborted = "daily LLM quota exhausted - rerun later to resume"
                break

        cache[claim] = result
        save_cache(cache)  # incremental: a crash never loses completed claims
        if args.delay:
            time.sleep(args.delay)

    # Metrics only count halves produced under THIS config; stale halves from
    # another setup stay on disk but are never mixed into the numbers.
    scored = []
    for r in claims:
        row = cache.get(r["claim"])
        if row is None:
            continue
        row = dict(row, label=r["label"])
        if half_is_cached(row, "argus_raw_probability", "argus_key", a_key):
            apply_current_calibrator(row, calibrator)
        else:
            row["argus_probability"] = None
        if args.no_baseline or not half_is_cached(row, "baseline_probability", "baseline_key", b_key):
            row["baseline_probability"] = None
        scored.append(row)
    save_cache(cache)

    summary = summarise(scored, args.bins, config)
    if aborted:
        summary["aborted"] = aborted
    SUMMARY.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print("\n" + "=" * 60)
    if aborted:
        print(f"ABORTED: {aborted}\n")
    for name in ("argus", "baseline"):
        s = summary[name]
        if not s["n"]:
            print(f"{name:9} no scored claims")
            continue
        print(f"{name:9} n={s['n']:<4} ({s['n_true']}T/{s['n_false']}F)  "
              f"accuracy={s['accuracy']:.3f}  ECE={s['ece']:.3f}  "
              f"mean P={s['mean_probability']:.3f}")
    print("=" * 60)
    print(f"per-claim -> {RESULTS}\nsummary   -> {SUMMARY}")


if __name__ == "__main__":
    main()
