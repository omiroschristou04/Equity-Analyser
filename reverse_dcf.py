import sys

import yfinance as yf

from wacc import calculate_wacc
from analyse import OUT_OF_SCOPE_SECTORS, SCOPE_MESSAGE

TERMINAL_GROWTH = 0.025
STAGE1_YEARS = 5
FADE_YEARS = 5

# Revenue CAGR is meaningless when the oldest period is a tiny fraction of the
# latest: a near-zero base makes the ratio explode (LXRX's $139k -> $49.8m base
# yields a 610% CAGR), which silently defeats the implied-growth plausibility
# check below (nothing in 2-30% can exceed 1.5x of 610%). Require the oldest
# revenue to be at least this fraction of the latest, else suppress the CAGR.
MIN_CAGR_BASE_FRACTION = 0.10

# yfinance labels D&A differently by industry (energy uses depletion wording).
DA_ROWS = (
    'Depreciation And Amortization',
    'Depreciation Amortization Depletion',
    'Depreciation Depletion And Amortization',
)


def _clean(series):
    return [x for x in series if x == x]


def _row0(df, name):
    try:
        v = df.loc[name].iloc[0]
        return float(v) if v == v else None
    except Exception:
        return None


def _first_row0(df, names):
    for n in names:
        v = _row0(df, n)
        if v is not None:
            return v
    return None


def _hist_rev_cagr(revenue):
    """CAGR of a newest-first revenue series.

    Returns (cagr, suppressed). `suppressed` is True when the oldest revenue is
    below MIN_CAGR_BASE_FRACTION of the latest — a near-zero base that would make
    the CAGR explode and mislead (LXRX: 610%). `cagr` is None when suppressed or
    when the series is too short or non-positive.
    """
    if len(revenue) >= 2 and revenue[-1] > 0:
        if revenue[-1] < revenue[0] * MIN_CAGR_BASE_FRACTION:
            return None, True
        years = len(revenue) - 1
        return (revenue[0] / revenue[-1]) ** (1 / years) - 1, False
    return None, False


def _net_debt(bs):
    """Net debt, falling back to Total Debt - Cash when the row is absent
    (net-cash names like ARM/MRNA report no 'Net Debt')."""
    nd = _row0(bs, 'Net Debt')
    if nd is not None:
        return nd
    total_debt = _row0(bs, 'Total Debt') or 0.0
    cash = (
        _row0(bs, 'Cash And Cash Equivalents')
        or _row0(bs, 'Cash Cash Equivalents And Short Term Investments')
        or 0.0
    )
    return total_debt - cash


def reverse_dcf(ticker):
    """Back out the FCF growth the market price implies, with plausibility flags.

    Returns a structured dict; never raises for missing fields. If the model
    genuinely can't be built (no EBIT, no share count, or WACC <= terminal
    growth), returns error set and rows empty.
    """
    ticker = ticker.upper()
    stock = yf.Ticker(ticker)
    info = stock.info or {}
    sector = info.get('sector')

    if sector in OUT_OF_SCOPE_SECTORS:
        return {'ticker': ticker, 'sector': sector, 'out_of_scope': True,
                'scope_message': SCOPE_MESSAGE}

    fin = stock.financials
    bs = stock.balance_sheet
    cf = stock.cashflow

    ebit = _row0(fin, 'EBIT')
    tax_rate = _row0(fin, 'Tax Rate For Calcs')
    d_and_a = _first_row0(cf, DA_ROWS) or 0.0
    capex_reported = _row0(cf, 'Capital Expenditure')
    try:
        dnwc_vals = _clean(cf.loc['Change In Working Capital'])
        delta_nwc = sum(dnwc_vals) / len(dnwc_vals) if dnwc_vals else 0.0
    except Exception:
        delta_nwc = 0.0

    shares = _row0(bs, 'Ordinary Shares Number')
    net_debt = _net_debt(bs)

    current_price = info.get('currentPrice') or info.get('regularMarketPrice')
    if current_price is None:
        h = stock.history(period="5d")
        current_price = float(h['Close'].iloc[-1]) if len(h) else None

    result = {
        'ticker': ticker,
        'sector': sector,
        'out_of_scope': False,
        'error': None,
        'terminal_growth': TERMINAL_GROWTH,
        'stage1_years': STAGE1_YEARS,
        'fade_years': FADE_YEARS,
        'reported_capex': capex_reported,
        'da_maintenance': -d_and_a if d_and_a else None,
        'avg_delta_nwc': delta_nwc,
        'current_price': current_price,
        'rows': [],
        'implied_growth': None,
        'implied_tv_share': None,
        'reconciled': False,
        'flags': [],
    }

    if ebit is None or tax_rate is None or shares in (None, 0):
        result['error'] = "Missing EBIT, tax rate or share count — cannot build model."
        return result

    # Normalised base FCF. Maintenance capex proxied by D&A, which cancels the
    # D&A add-back, so base_fcf = NOPAT + avg change in working capital.
    nopat = ebit * (1 - tax_rate)
    maintenance_capex = -d_and_a
    base_fcf = nopat + d_and_a + maintenance_capex + delta_nwc
    result['nopat'] = nopat
    result['base_fcf'] = base_fcf
    result['net_debt'] = net_debt
    result['shares'] = shares

    try:
        wacc = calculate_wacc(ticker)['wacc']
    except Exception as exc:
        result['error'] = f"WACC unavailable ({exc.__class__.__name__})."
        return result
    result['wacc'] = wacc

    if wacc <= TERMINAL_GROWTH:
        result['error'] = (
            f"WACC ({wacc:.2%}) <= terminal growth ({TERMINAL_GROWTH:.2%}); "
            "terminal value undefined."
        )
        return result

    revenue = _clean(fin.loc['Total Revenue']) if 'Total Revenue' in fin.index else []
    # Suppression (near-zero base) keeps a 610% CAGR from silently disabling the
    # plausibility check below — see _hist_rev_cagr.
    result['hist_rev_cagr'], result['hist_rev_cagr_suppressed'] = _hist_rev_cagr(revenue)

    def value_at_growth(g):
        flows = []
        fcf = base_fcf
        for _ in range(STAGE1_YEARS):
            fcf = fcf * (1 + g)
            flows.append(fcf)
        for i in range(1, FADE_YEARS + 1):
            fade_g = g + (TERMINAL_GROWTH - g) * i / FADE_YEARS
            fcf = fcf * (1 + fade_g)
            flows.append(fcf)
        discounted = [f / (1 + wacc) ** y for y, f in enumerate(flows, start=1)]
        total_years = STAGE1_YEARS + FADE_YEARS
        tv = flows[-1] * (1 + TERMINAL_GROWTH) / (wacc - TERMINAL_GROWTH)
        discounted_tv = tv / (1 + wacc) ** total_years
        ev = sum(discounted) + discounted_tv
        equity = ev - net_debt
        tv_share = discounted_tv / ev if ev else float('nan')
        return equity / shares, tv_share

    for i in range(2, 31):
        g = i / 100
        v, tv_share = value_at_growth(g)
        is_market = current_price is not None and abs(v - current_price) < current_price * 0.02
        if is_market:
            result['implied_growth'] = g
            result['implied_tv_share'] = tv_share
            result['reconciled'] = True
        result['rows'].append({
            'growth': g, 'value': v, 'tv_share': tv_share, 'is_market': is_market,
        })

    # Plausibility flags.
    g = result['implied_growth']
    cagr = result['hist_rev_cagr']
    if result['reconciled']:
        if result['hist_rev_cagr_suppressed']:
            result['flags'].append(
                "Historical revenue CAGR cannot be evaluated: the oldest revenue "
                f"in the series is below {MIN_CAGR_BASE_FRACTION:.0%} of the latest, "
                "so its growth rate explodes off a near-zero base. The implied-growth "
                "plausibility check was not applied — do not read its silence as a pass."
            )
        elif cagr is not None and cagr > 0 and g > cagr * 1.5:
            result['flags'].append(
                f"Implied growth {g:.0%} far exceeds historical revenue CAGR "
                f"{cagr:.1%}. Model cannot value this name credibly — treat as diagnostic."
            )
        if result['implied_tv_share'] is not None and result['implied_tv_share'] > 0.75:
            result['flags'].append(
                f"Terminal value is {result['implied_tv_share']:.0%} of EV. "
                "You are valuing an assumption, not cash flows."
            )
    else:
        result['flags'].append(
            "No growth rate in 2-30% reconciles to the market price. "
            + ("Base FCF is negative - the DCF cannot value a loss-maker on current cash flows."
               if base_fcf < 0 else "Check the base - model cannot reconcile to price.")
        )

    return result


# --- CLI presentation ---

def print_report(result):
    if result.get('out_of_scope'):
        print(result['scope_message'])
        return
    print(f"{result['ticker']} reverse DCF")
    if result.get('error'):
        print(f"FLAG: {result['error']}")
        return
    dm = result['da_maintenance']
    print(f"Reported capex: {result['reported_capex']:,.0f}"
          if result['reported_capex'] is not None else "Reported capex: n/a")
    print(f"D&A (maintenance proxy): {dm:,.0f}" if dm is not None else "D&A: n/a")
    print(f"Avg delta NWC: {result['avg_delta_nwc']:,.0f}")
    print(f"Normalised base FCF: {result['base_fcf']:,.0f}")
    print(f"WACC: {result['wacc']:.2%}")
    print(f"Terminal growth: {result['terminal_growth']:.1%}")
    print(f"Structure: {result['stage1_years']}yr growth, "
          f"{result['fade_years']}yr fade, then terminal")
    cagr = result['hist_rev_cagr']
    print(f"Historical revenue CAGR: {cagr:.1%}" if cagr is not None else
          "Historical revenue CAGR: n/a")
    print(f"Current price: {result['current_price']:.2f}"
          if result['current_price'] is not None else "Current price: n/a")
    print()
    print("Growth  ->  Value/share   TV% of EV")
    for row in result['rows']:
        marker = "  <-- market" if row['is_market'] else ""
        print(f"{row['growth']:>5.0%}  ->  {row['value']:9.2f}     "
              f"{row['tv_share']:5.0%}{marker}")
    print()
    if result['reconciled']:
        print(f"IMPLIED 5YR FCF GROWTH: {result['implied_growth']:.0%}")
    for flag in result['flags']:
        print(f"FLAG: {flag}")


if __name__ == "__main__":
    tk = sys.argv[1] if len(sys.argv) > 1 else "MSFT"
    print_report(reverse_dcf(tk))
