"""Metrics used by the offline eval harness. Pure math, no LLM, no files."""
from scripts.evaluate import accuracy, bin_stats, ece


def test_accuracy_threshold():
    probs = [0.9, 0.6, 0.4, 0.1]
    labels = [True, False, True, False]
    # 0.9->True hit, 0.6->True miss, 0.4->False miss, 0.1->False hit
    assert accuracy(probs, labels) == 0.5
    assert accuracy([], []) is None


def test_perfectly_calibrated_has_zero_ece():
    # Two bins: everything at 0.0 is false, everything at 1.0 is true.
    probs = [0.0, 0.0, 1.0, 1.0]
    labels = [False, False, True, True]
    assert ece(probs, labels, bins=10) == 0.0
    assert accuracy(probs, labels) == 1.0


def test_maximally_miscalibrated_ece_is_one():
    # Confidently wrong every time.
    probs = [1.0, 1.0, 0.0, 0.0]
    labels = [False, False, True, True]
    assert ece(probs, labels, bins=10) == 1.0


def test_bins_cover_the_unit_interval():
    probs = [0.0, 0.05, 0.5, 0.99, 1.0]
    labels = [False, False, True, True, True]
    stats = bin_stats(probs, labels, bins=10)
    assert len(stats) == 10
    # every probability lands in exactly one bin, 1.0 included
    assert sum(b["count"] for b in stats) == len(probs)
    assert stats[0]["count"] == 2          # 0.0 and 0.05
    assert stats[5]["count"] == 1          # 0.5
    assert stats[9]["count"] == 2          # 0.99 and 1.0
    assert stats[1]["confidence"] is None  # empty bin, not a zero


def test_empty_input():
    assert ece([], [], bins=10) is None
