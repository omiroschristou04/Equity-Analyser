"""Regression tests for data-shape traps we have actually hit.

Each test pins one bug that came from the *shape* of upstream data rather than
a logic error: a near-zero revenue base, a newest-first series read as if it
were oldest-first, and a numpy scalar standing in for a Python bool. Run with:

    python -m pytest test_data_shape_traps.py
"""

import numpy as np

from reverse_dcf import _hist_rev_cagr, MIN_CAGR_BASE_FRACTION
from criteria import bajaj_compounder, buffett_quality


def test_near_zero_revenue_base_suppresses_cagr():
    """LXRX: a tiny oldest revenue makes the CAGR explode (610%), which silently
    defeats the implied-growth plausibility check. Such a series must suppress
    the CAGR, while genuine growers keep theirs."""
    # newest -> oldest, oldest is 0.28% of newest (the real LXRX shape).
    lxrx = [49_803_000, 31_081_000, 1_204_000, 139_000]
    cagr, suppressed = _hist_rev_cagr(lxrx)
    assert suppressed is True
    assert cagr is None

    # A high but genuine grower (RIVN: oldest is ~31% of newest) is NOT suppressed.
    rivn = [5_387_000_000, 4_970_000_000, 4_434_000_000, 1_658_000_000]
    cagr, suppressed = _hist_rev_cagr(rivn)
    assert suppressed is False
    assert cagr is not None and cagr > 0

    # The boundary is the named constant, not a magic number: a base exactly at
    # the threshold is kept, a hair below is suppressed.
    at_threshold = [100.0, MIN_CAGR_BASE_FRACTION * 100.0]
    assert _hist_rev_cagr(at_threshold)[1] is False
    just_below = [100.0, MIN_CAGR_BASE_FRACTION * 100.0 - 0.01]
    assert _hist_rev_cagr(just_below)[1] is True


def test_share_count_history_is_newest_first():
    """no_dilution compares share_count_history[0] (newest) to [-1] (oldest).
    yfinance returns the series newest-first, so a company whose share count
    GREW over time must fail no_dilution, and a buyback company must pass."""
    base = dict(
        revenue_growth_5yr=[5.0, 6.0, 5.5, 6.2],
        roe_history=[18.0, 19.0, 17.0, 16.0],
        roic=0.12,
        wacc=0.08,
    )

    # Dilution: newest count (24) is larger than the oldest (10) -> must fail.
    diluted = bajaj_compounder(share_count_history=[24, 20, 15, 10], **base)
    assert diluted['no_dilution'] is False

    # Buyback: newest count (10) is smaller than the oldest (24) -> must pass.
    bought_back = bajaj_compounder(share_count_history=[10, 15, 20, 24], **base)
    assert bought_back['no_dilution'] is True


def test_numpy_bool_does_not_break_score_counting():
    """The score idiom sums `v is True`; a numpy.bool_(True) is NOT `is True`,
    so any check leaking a numpy scalar would vanish from the score. Pin both the
    trap and the defence: criteria functions wrap every check in bool(), so numpy
    inputs still yield genuine Python bools that the score counts."""
    # The trap itself: numpy booleans are silently dropped by `is True`.
    assert (np.bool_(True) is True) is False
    leaky = {'a': np.bool_(True), 'b': np.bool_(True)}
    assert sum(1 for v in leaky.values() if v is True) == 0

    # The defence: numpy-typed inputs still produce real Python bools and a
    # correct score.
    checks = buffett_quality(
        roe_5yr=[np.float64(20), np.float64(18)],       # both > 15
        debt_to_equity=np.float64(0.3),                 # < 0.5
        fcf_history=[np.float64(1.0), np.float64(2.0)],  # all > 0
    )
    non_score = {k: v for k, v in checks.items() if k != 'score'}
    assert all(type(v) is bool for v in non_score.values())
    assert checks['score'] == sum(1 for v in non_score.values() if v is True)
    assert checks['score'] == 3
