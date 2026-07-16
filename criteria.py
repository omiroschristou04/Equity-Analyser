import statistics


def buffett_quality(roe_5yr, debt_to_equity, fcf_history):
    checks = {}
    checks['roe_above_15'] = bool(all(r > 15 for r in roe_5yr))
    checks['low_leverage'] = bool(debt_to_equity < 0.5)
    checks['consistent_fcf'] = bool(all(f > 0 for f in fcf_history))
    checks['score'] = sum(1 for k, v in checks.items() if v is True)
    return checks


def lynch_garp(peg, earnings_growth, inventory_growth, sales_growth):
    checks = {}
    checks['peg_below_1'] = bool(peg < 1)
    checks['growth_in_band'] = bool(15 < earnings_growth < 25)
    checks['inventory_ok'] = bool(inventory_growth < sales_growth)
    checks['score'] = sum(1 for k, v in checks.items() if v is True)
    return checks


def graham_value(pb, current_ratio, earnings_history):
    checks = {}
    checks['pb_below_1_5'] = bool(pb < 1.5)
    checks['current_ratio_above_2'] = bool(current_ratio > 2)
    checks['positive_earnings'] = bool(all(e > 0 for e in earnings_history))
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
    checks['above_200ma'] = bool(price > ma_200)
    checks['no_volume_confirmed_decline'] = bool(not volume_spike_on_decline)
    checks['score'] = sum(1 for k, v in checks.items() if v is True)
    return checks


def inglis_jones_gleave(fcf_yield, sector_fcf_yield, momentum_12_1):
    checks = {}
    checks['fcf_above_sector'] = bool(fcf_yield > sector_fcf_yield)
    checks['positive_momentum'] = bool(momentum_12_1 > 0)
    checks['passes_both'] = bool(
        checks['fcf_above_sector'] and checks['positive_momentum']
    )
    checks['score'] = sum(1 for k, v in checks.items() if v is True)
    return checks


def bajaj_compounder(revenue_growth_5yr, roe_history, roic, wacc, share_count_history):
    """Durability, not speed. Bajaj asks whether the business compounds, not how fast."""
    checks = {}
    checks['growth_every_year'] = bool(all(g > 0 for g in revenue_growth_5yr))
    checks['growth_stable'] = bool(statistics.stdev(revenue_growth_5yr) < 10)
    recent_roe = statistics.mean(roe_history[:2])
    older_roe = statistics.mean(roe_history[2:])
    checks['roe_not_eroding'] = bool(recent_roe >= older_roe)
    checks['roic_above_wacc'] = bool(roic > wacc)
    checks['no_dilution'] = bool(share_count_history[0] <= share_count_history[-1])
    checks['score'] = sum(1 for k, v in checks.items() if v is True)
    return checks
