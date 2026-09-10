"""Class balancing for the FEVER sample. Pure function, no download."""
import random

from scripts.prepare_fever import balance


def _rows(n_true, n_false):
    return ([(f"true claim {i}", True) for i in range(n_true)]
            + [(f"false claim {i}", False) for i in range(n_false)])


def _counts(sample):
    n_true = sum(1 for _, lb in sample if lb)
    return n_true, len(sample) - n_true


def test_balance_even_split():
    assert _counts(balance(_rows(100, 100), 50, random.Random(42))) == (25, 25)
    assert _counts(balance(_rows(100, 100), 100, random.Random(42))) == (50, 50)


def test_balance_skewed_source_stays_even():
    # A 9:1 source must still yield a 50/50 sample, not mirror the skew.
    assert _counts(balance(_rows(900, 100), 50, random.Random(42))) == (25, 25)


def test_balance_short_class_caps_both_sides():
    # Only 5 REFUTED available: both classes cap at 5 rather than padding to 50.
    assert _counts(balance(_rows(30, 5), 50, random.Random(42))) == (5, 5)


def test_balance_odd_n_rounds_down():
    assert _counts(balance(_rows(100, 100), 51, random.Random(42))) == (25, 25)


def test_balance_reproducible_by_seed():
    rows = _rows(100, 100)
    assert balance(rows, 50, random.Random(42)) == balance(rows, 50, random.Random(42))
    assert balance(rows, 50, random.Random(42)) != balance(rows, 50, random.Random(7))
    # Independent of source row order, too.
    assert balance(rows, 50, random.Random(42)) == balance(rows[::-1], 50, random.Random(42))


def test_balance_dedupes_and_drops_ambiguous_claims():
    rows = _rows(10, 10) + [("true claim 0", True)] * 3 + [("contested", True), ("contested", False)]
    sample = balance(rows, 40, random.Random(42))
    claims = [c for c, _ in sample]
    assert len(claims) == len(set(claims))   # no duplicates
    assert "contested" not in claims          # both labels seen -> dropped
    assert _counts(sample) == (10, 10)
