import statistics

# All checks are None- and short-history-tolerant: a metric that is missing
# (None) or that can't be computed from too few years fails the criterion rather
# than raising. For fully-populated inputs the pass/fail semantics are unchanged.


def buffett_quality(roe_5yr, debt_to_equity, fcf_history):
    checks = {}
    checks['roe_above_15'] = bool(roe_5yr and all(r > 15 for r in roe_5yr))
    checks['low_leverage'] = bool(debt_to_equity is not None and debt_to_equity < 0.5)
    checks['consistent_fcf'] = bool(fcf_history and all(f > 0 for f in fcf_history))
    checks['score'] = sum(1 for k, v in checks.items() if v is True)
    return checks


def lynch_garp(peg, earnings_growth, inventory_growth, sales_growth):
    checks = {}
    checks['peg_below_1'] = bool(peg is not None and peg < 1)
    checks['growth_in_band'] = bool(
        earnings_growth is not None and 15 < earnings_growth < 25
    )
    checks['inventory_ok'] = bool(
        inventory_growth is not None
        and sales_growth is not None
        and inventory_growth < sales_growth
    )
    checks['score'] = sum(1 for k, v in checks.items() if v is True)
    return checks


def graham_value(pb, current_ratio, earnings_history):
    checks = {}
    checks['pb_below_1_5'] = bool(pb is not None and pb < 1.5)
    checks['current_ratio_above_2'] = bool(
        current_ratio is not None and current_ratio > 2
    )
    checks['positive_earnings'] = bool(
        earnings_history and all(e > 0 for e in earnings_history)
    )
    checks['score'] = sum(1 for k, v in checks.items() if v is True)
    return checks


def greenblatt_magic(ey_percentile, roic_percentile):
    """Greenblatt ranks rather than sets thresholds. Percentiles vs sector, 0-100.

    Returns (checks, combined_rank). combined_rank is a diagnostic sum of the two
    percentiles, not a pass/fail rule, so it is returned separately rather than
    living inside `checks` where a truthiness-based score would miscount it.
    """
    checks = {}
    checks['ey_top_quartile'] = bool(ey_percentile >= 75)
    checks['roic_top_quartile'] = bool(roic_percentile >= 75)
    combined_rank = ey_percentile + roic_percentile
    checks['score'] = sum(1 for k, v in checks.items() if v is True)
    return checks, combined_rank


def goldberg_technical(price, ma_200, volume_spike_on_decline):
    checks = {}
    # ma_200 is NaN when history is shorter than 200 sessions; NaN != NaN, so the
    # `ma_200 == ma_200` test rejects it and the criterion fails rather than
    # comparing against NaN.
    checks['above_200ma'] = bool(
        price is not None and ma_200 == ma_200 and price > ma_200
    )
    checks['no_volume_confirmed_decline'] = bool(not volume_spike_on_decline)
    checks['score'] = sum(1 for k, v in checks.items() if v is True)
    return checks


def inglis_jones_gleave(fcf_yield, sector_fcf_yield, momentum_12_1):
    checks = {}
    checks['fcf_above_sector'] = bool(
        fcf_yield is not None
        and sector_fcf_yield is not None
        and fcf_yield > sector_fcf_yield
    )
    checks['positive_momentum'] = bool(
        momentum_12_1 is not None and momentum_12_1 > 0
    )
    checks['passes_both'] = bool(
        checks['fcf_above_sector'] and checks['positive_momentum']
    )
    checks['score'] = sum(1 for k, v in checks.items() if v is True)
    return checks


def bajaj_compounder(revenue_growth_5yr, roe_history, roic, wacc, share_count_history):
    """Durability, not speed. Bajaj asks whether the business compounds, not how fast."""
    checks = {}
    checks['growth_every_year'] = bool(
        revenue_growth_5yr and all(g > 0 for g in revenue_growth_5yr)
    )
    # stdev needs >= 2 points; a split-mean comparison of ROE needs >= 3.
    checks['growth_stable'] = bool(
        len(revenue_growth_5yr) >= 2 and statistics.stdev(revenue_growth_5yr) < 10
    )
    if len(roe_history) >= 3:
        recent_roe = statistics.mean(roe_history[:2])
        older_roe = statistics.mean(roe_history[2:])
        checks['roe_not_eroding'] = bool(recent_roe >= older_roe)
    else:
        checks['roe_not_eroding'] = False
    checks['roic_above_wacc'] = bool(
        roic is not None and wacc is not None and roic > wacc
    )
    checks['no_dilution'] = bool(
        len(share_count_history) >= 2
        and share_count_history[0] <= share_count_history[-1]
    )
    checks['score'] = sum(1 for k, v in checks.items() if v is True)
    return checks
