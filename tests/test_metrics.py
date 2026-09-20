"""Ranking, scoring and paired-significance metrics. Pure math, no LLM, no files."""
import math

import pytest

from scripts.metrics import auroc, brier, mcnemar, threshold_sweep


# --- AUROC ------------------------------------------------------------------

def test_auroc_perfect_separation():
    assert auroc([0.9, 0.8, 0.2, 0.1], [True, True, False, False]) == 1.0


def test_auroc_inverted_separation():
    assert auroc([0.1, 0.2, 0.8, 0.9], [True, True, False, False]) == 0.0


def test_auroc_all_ties_is_chance():
    # Every score identical -> the ranker carries no information.
    assert auroc([0.5] * 4, [True, True, False, False]) == 0.5


def test_auroc_handles_partial_ties():
    # Ranks: 0.1->1, 0.5->2.5, 0.5->2.5, 0.9->4. Positives are 0.9 and one 0.5.
    # sum(pos ranks)=4+2.5=6.5; U = 6.5 - 2*3/2 = 3.5; AUROC = 3.5/(2*2) = 0.875
    assert auroc([0.1, 0.5, 0.5, 0.9], [False, False, True, True]) == pytest.approx(0.875)


def test_auroc_is_none_without_both_classes():
    assert auroc([0.1, 0.9], [True, True]) is None
    assert auroc([], []) is None


def test_auroc_is_invariant_to_monotone_rescaling():
    probs = [0.05, 0.31, 0.44, 0.62, 0.88]
    labels = [False, False, True, False, True]
    squashed = [p / 10 + 0.4 for p in probs]  # order-preserving
    assert auroc(squashed, labels) == pytest.approx(auroc(probs, labels))


# --- Brier ------------------------------------------------------------------

def test_brier_perfect_and_worst():
    assert brier([1.0, 0.0], [True, False]) == 0.0
    assert brier([0.0, 1.0], [True, False]) == 1.0


def test_brier_always_half():
    assert brier([0.5] * 4, [True, False, True, False]) == pytest.approx(0.25)


def test_brier_is_none_when_empty():
    assert brier([], []) is None


# --- threshold sweep --------------------------------------------------------

def test_threshold_sweep_finds_the_better_cut():
    # Scores parked low: 0.5 misclassifies both positives, 0.25 gets them right.
    probs = [0.3, 0.35, 0.1, 0.05]
    labels = [True, True, False, False]
    sweep = {round(row["threshold"], 2): row["accuracy"] for row in threshold_sweep(probs, labels)}
    assert sweep[0.5] == 0.5
    assert sweep[0.25] == 1.0


def test_threshold_sweep_covers_the_unit_interval():
    sweep = threshold_sweep([0.4], [True], step=0.25)
    assert [round(r["threshold"], 2) for r in sweep] == [0.0, 0.25, 0.5, 0.75, 1.0]


# --- McNemar ----------------------------------------------------------------

def test_mcnemar_no_discordant_pairs_is_p_one():
    # Both systems right on the same claims -> nothing to distinguish them.
    correct_a = [True, True, False, False]
    correct_b = [True, True, False, False]
    r = mcnemar(correct_a, correct_b)
    assert r["n_discordant"] == 0
    assert r["p_value"] == 1.0


def test_mcnemar_counts_discordant_pairs_directionally():
    #            a right/b wrong ->b_only=0, a_only=2 ; a wrong/b right -> 1
    correct_a = [True, True, False, True]
    correct_b = [False, False, True, True]
    r = mcnemar(correct_a, correct_b)
    assert r["a_only"] == 2
    assert r["b_only"] == 1
    assert r["n_discordant"] == 3


def test_mcnemar_exact_binomial_p_value():
    # 6 discordant pairs, all favouring b. Two-sided exact = 2 * 0.5**6 = 0.03125
    correct_a = [False] * 6
    correct_b = [True] * 6
    r = mcnemar(correct_a, correct_b)
    assert r["a_only"] == 0 and r["b_only"] == 6
    assert r["p_value"] == pytest.approx(2 * 0.5 ** 6)


def test_mcnemar_p_value_never_exceeds_one():
    # An even split is the most likely outcome; the doubled tail must be clamped.
    correct_a = [True, False]
    correct_b = [False, True]
    r = mcnemar(correct_a, correct_b)
    assert r["p_value"] == 1.0


def test_mcnemar_uses_exact_test_not_chi_square_at_small_n():
    # 5 discordant pairs all one way. Chi-square with continuity correction gives
    # p ~= 0.0253; the exact binomial gives 2*0.5**5 = 0.0625. At this n the exact
    # test is the correct one and the difference straddles alpha=0.05.
    r = mcnemar([False] * 5, [True] * 5)
    assert r["p_value"] == pytest.approx(0.0625)
    assert r["p_value"] > 0.05


def test_mcnemar_rejects_mismatched_lengths():
    with pytest.raises(ValueError):
        mcnemar([True, False], [True])


# --- cross-checks -----------------------------------------------------------

def test_brier_and_auroc_disagree_on_a_miscalibrated_ranker():
    """The whole diagnosis in the spec rests on this distinction: a system can
    rank well (high AUROC) while being badly scored (high Brier) because its
    probabilities sit in the wrong part of the range."""
    probs = [0.30, 0.25, 0.20, 0.15]  # perfectly ranked, all far too low
    labels = [True, True, False, False]
    assert auroc(probs, labels) == 1.0
    assert brier(probs, labels) > 0.2
    assert not math.isclose(brier(probs, labels), 0.0)
