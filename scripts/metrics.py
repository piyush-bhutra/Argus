"""Evaluation metrics for the offline harness.

Pure math over (probabilities, labels). No LLM, no network, no file IO — so
scripts/rescore.py can import this and still guarantee it never makes an API call.

`accuracy`, `bin_stats` and `ece` live here too, re-exported by scripts/evaluate.py
so existing imports keep working. Everything that bins probabilities must use the
same binning, or the reliability diagrams stop matching the reported ECE.
"""
import math

__all__ = [
    "accuracy", "bin_stats", "ece",
    "auroc", "brier", "threshold_sweep", "mcnemar",
]


# --- calibration ------------------------------------------------------------

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


# --- ranking and scoring ----------------------------------------------------

def _midranks(values):
    """1-based ranks, ties sharing their average rank (the standard correction)."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        shared = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = shared
        i = j + 1
    return ranks


def auroc(probs, labels):
    """Area under the ROC curve, via the Mann-Whitney U identity.

    Ties get midranks, so a system that outputs one constant score scores 0.5
    rather than an arbitrary value. Returns None unless both classes are present —
    AUROC is undefined otherwise, and returning 0.5 there would silently report
    chance performance for a set that simply has no negatives.
    """
    n_pos = sum(1 for lb in labels if lb)
    n_neg = len(labels) - n_pos
    if not n_pos or not n_neg:
        return None
    ranks = _midranks(probs)
    rank_sum = sum(r for r, lb in zip(ranks, labels) if lb)
    return (rank_sum - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg)


def brier(probs, labels):
    """Mean squared error of the probability against the 0/1 outcome.

    Unlike ECE this is a strictly proper scoring rule: it penalises a system for
    being confidently wrong, not merely for being miscalibrated in aggregate.
    """
    if not probs:
        return None
    return sum((p - bool(lb)) ** 2 for p, lb in zip(probs, labels)) / len(probs)


def threshold_sweep(probs, labels, step=0.05):
    """Accuracy across decision thresholds from 0.0 to 1.0 inclusive.

    Reported as a diagnostic, never used to pick an operating point — choosing the
    best threshold on the evaluation set is fitting on it.
    """
    n_steps = int(round(1.0 / step))
    out = []
    for i in range(n_steps + 1):
        t = i * step
        out.append({"threshold": t, "accuracy": accuracy(probs, labels, t)})
    return out


# --- paired significance ----------------------------------------------------

def _binom_tail(k, n):
    """P(X <= k) for X ~ Binomial(n, 0.5)."""
    return sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n


def mcnemar(correct_a, correct_b):
    """Exact two-sided McNemar test on paired correctness vectors.

    Both systems score the SAME claims, so the paired test is far tighter than
    comparing two independent accuracies — at n=50 the unpaired CI is about
    +/-0.13 and establishes nothing.

    The exact binomial test is used rather than the chi-square approximation: with
    a handful of discordant pairs the approximation is anticonservative and can
    manufacture significance that is not there.

    Returns a_only (a right, b wrong), b_only, n_discordant and the p-value.
    """
    if len(correct_a) != len(correct_b):
        raise ValueError(
            f"paired test needs equal-length vectors, got {len(correct_a)} and {len(correct_b)}"
        )
    a_only = sum(1 for a, b in zip(correct_a, correct_b) if a and not b)
    b_only = sum(1 for a, b in zip(correct_a, correct_b) if b and not a)
    n = a_only + b_only

    if n == 0:
        p = 1.0
    else:
        p = min(1.0, 2 * _binom_tail(min(a_only, b_only), n))

    return {"a_only": a_only, "b_only": b_only, "n_discordant": n, "p_value": p}
