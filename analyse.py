import sys

import yfinance as yf

from wacc import calculate_wacc
from criteria import (
    buffett_quality,
    lynch_garp,
    graham_value,
    goldberg_technical,
    bajaj_compounder,
    greenblatt_magic,
    inglis_jones_gleave,
)
from peers import peer_analysis

# Financials and REITs are out of scope: enterprise value, capex, unlevered FCF
# and ROIC-vs-WACC are undefined for them. The tool exits rather than emit a
# NaN-filled, misleading report.
OUT_OF_SCOPE_SECTORS = ('Financial Services', 'Real Estate')
SCOPE_MESSAGE = (
    "This tool does not cover financials or REITs. Banks have no meaningful\n"
    "enterprise value, capex, or unlevered free cash flow — debt is raw material,\n"
    "not financing. They are valued on P/B against ROTE, or via a dividend\n"
    "discount model. That is a different framework, not a variant of this one."
)


def _clean(series):
    """List of a statement row's values, newest-first, with NaN padding dropped."""
    return [x for x in series if x == x]


def _row_list(df, name):
    try:
        return _clean(df.loc[name])
    except Exception:
        return []


def _row0(df, name):
    try:
        v = df.loc[name].iloc[0]
        return float(v) if v == v else None
    except Exception:
        return None


def _pct(x):
    """Fraction -> percent, passing None through (yfinance gives None for
    unavailable growth/ratio fields on loss-makers)."""
    return x * 100 if x is not None else None


def _package(checks, diagnostics=None):
    """Split a criteria dict into score/total/rules(+optional diagnostics)."""
    score = checks.pop('score')
    return {
        'score': score,
        'total': len(checks),      # all remaining entries are pass/fail bools
        'rules': dict(checks),
        'diagnostics': diagnostics or {},
    }


def analyse(ticker, peer_verbose=False):
    """Run the full analysis for `ticker` and return a structured result dict.

    Never raises for merely-missing fields: unavailable metrics become None and
    the dependent checklist criterion fails rather than crashing. Financials and
    REITs short-circuit with out_of_scope=True.
    """
    ticker = ticker.upper()
    stock = yf.Ticker(ticker)
    info = stock.info or {}
    sector = info.get('sector')

    if sector in OUT_OF_SCOPE_SECTORS:
        return {
            'ticker': ticker,
            'sector': sector,
            'out_of_scope': True,
            'scope_message': SCOPE_MESSAGE,
        }

    fin = stock.financials
    bs = stock.balance_sheet
    cf = stock.cashflow
    notes = []

    net_income = _row_list(fin, 'Net Income')
    equity = _row_list(bs, 'Stockholders Equity')
    revenue = _row_list(fin, 'Total Revenue')
    ocf = _row_list(cf, 'Operating Cash Flow')
    capex = _row_list(cf, 'Capital Expenditure')  # reported negative

    roe_history = [n / e * 100 for n, e in zip(net_income, equity) if e]
    fcf_history = [o + c for o, c in zip(ocf, capex)]
    revenue_growth = [
        (revenue[i] / revenue[i + 1] - 1) * 100
        for i in range(len(revenue) - 1)
        if revenue[i + 1]
    ]

    dte_raw = info.get('debtToEquity')
    debt_to_equity = dte_raw / 100 if dte_raw is not None else None

    # WACC (robust to net-cash firms / missing beta).
    try:
        wacc_res = calculate_wacc(ticker)
        wacc = wacc_res['wacc']
        if wacc_res.get('beta_assumed'):
            notes.append("WACC uses an assumed beta of 1.0 (yfinance had none).")
    except Exception as exc:
        wacc = None
        notes.append(f"WACC unavailable ({exc.__class__.__name__}).")

    # ROIC = NOPAT / invested capital.
    ebit = _row0(fin, 'EBIT')
    tax_rate = _row0(fin, 'Tax Rate For Calcs')
    invested_capital = _row0(bs, 'Invested Capital')
    if ebit is not None and tax_rate is not None and invested_capital:
        roic = ebit * (1 - tax_rate) / invested_capital
    else:
        roic = None

    share_count_history = _row_list(bs, 'Ordinary Shares Number')

    # Price history / momentum / technicals.
    hist = stock.history(period="1y")
    closes = hist['Close'] if len(hist) else None
    if closes is not None and len(closes):
        price = float(closes.iloc[-1])
        ma_200 = float(closes.rolling(200).mean().iloc[-1])  # NaN if < 200 sessions
        worst_day = closes.pct_change().idxmin()
        volume_spike_on_decline = bool(
            hist.loc[worst_day, 'Volume'] > hist['Volume'].mean() * 1.5
        )
        if len(closes) > 22:
            momentum_12_1 = float((closes.iloc[-22] / closes.iloc[0] - 1) * 100)
        else:
            momentum_12_1 = float((closes.iloc[-1] / closes.iloc[0] - 1) * 100)
    else:
        price = ma_200 = momentum_12_1 = None
        volume_spike_on_decline = False
        notes.append("No price history available.")

    # Inventory (absent for many service businesses).
    inventory = _row_list(bs, 'Inventory')
    if len(inventory) >= 2 and inventory[1]:
        inventory_growth = (inventory[0] / inventory[1] - 1) * 100
    else:
        inventory_growth = None

    # Peer universe (sector-relative). Never let a peer/network hiccup abort the run.
    try:
        peer = peer_analysis(ticker, verbose=peer_verbose)
    except Exception as exc:
        peer = None
        notes.append(f"Peer universe unavailable ({exc.__class__.__name__}); "
                     "Greenblatt, Inglis-Jones and relative valuation skipped.")

    pct = peer['percentiles'] if peer else {}
    sector_median = peer['sector_median'] if peer else {}
    target_fcf_yield = peer['target']['fcf_yield'] if peer else None
    sector_fcf_yield = sector_median.get('fcf_yield') if peer else None

    # --- Checklists ---
    checklists = {}
    checklists['Buffett quality'] = _package(
        buffett_quality(roe_history, debt_to_equity, fcf_history)
    )
    checklists['Lynch GARP'] = _package(
        lynch_garp(
            info.get('trailingPegRatio'),
            _pct(info.get('earningsGrowth')),
            inventory_growth,
            _pct(info.get('revenueGrowth')),
        )
    )
    checklists['Graham value'] = _package(
        graham_value(info.get('priceToBook'), info.get('currentRatio'), net_income)
    )
    checklists['Goldberg technical'] = _package(
        goldberg_technical(price, ma_200, volume_spike_on_decline)
    )
    checklists['Bajaj compounder'] = _package(
        bajaj_compounder(
            revenue_growth,
            roe_history,
            roic * 100 if roic is not None else None,
            wacc * 100 if wacc is not None else None,
            share_count_history,
        )
    )

    if pct.get('earnings_yield') is not None and pct.get('roic') is not None:
        gb_checks, gb_combined = greenblatt_magic(pct['earnings_yield'], pct['roic'])
        checklists['Greenblatt magic'] = _package(
            gb_checks, {'combined_rank': gb_combined}
        )
    else:
        notes.append("Greenblatt magic skipped - no EY/ROIC percentiles.")

    if target_fcf_yield is not None and sector_fcf_yield is not None:
        checklists['Inglis-Jones / Gleave'] = _package(
            inglis_jones_gleave(target_fcf_yield, sector_fcf_yield, momentum_12_1)
        )
    else:
        notes.append("Inglis-Jones / Gleave skipped - no sector FCF yield.")

    # --- Relative valuation (lower percentile = cheaper) ---
    relative_valuation = []
    for key, label in [('pe', 'P/E'), ('ev_ebitda', 'EV/EBITDA'), ('pb', 'P/B')]:
        relative_valuation.append({
            'key': key,
            'label': label,
            'target': peer['target'][key] if peer else None,
            'median': sector_median.get(key) if peer else None,
            'percentile': pct.get(key) if peer else None,
            'n': peer['n_valid'][key] if peer else 0,
        })

    return {
        'ticker': ticker,
        'sector': sector,
        'out_of_scope': False,
        'header': {
            'long_name': info.get('longName') or ticker,
            'sector': sector,
            'price': price,
            'ma_200': ma_200,
            'wacc': wacc,
            'roic': roic,
            'momentum_12_1': momentum_12_1,
            'roe_history': roe_history,
        },
        'peer': peer,
        'relative_valuation': relative_valuation,
        'checklists': checklists,
        'notes': notes,
    }


# --- CLI presentation ---

def _f(v, pct=False, dp=2):
    if v is None or v != v:
        return "n/a"
    return f"{v*100:.{dp}f}%" if pct else f"{v:.{dp}f}"


def print_report(result):
    if result.get('out_of_scope'):
        print(result['scope_message'])
        return

    h = result['header']
    print(f"=== {h['long_name']} ({result['ticker']}) ===")
    print(f"Sector: {h['sector']}")
    print(f"Price: {_f(h['price'])}   200d MA: {_f(h['ma_200'])}")
    print(f"WACC: {_f(h['wacc'], pct=True)}   ROIC: {_f(h['roic'], pct=True)}")
    print(f"12-1 momentum: {_f(h['momentum_12_1'])}%   "
          "(feeds Inglis-Jones positive_momentum)")
    print(f"ROE (newest first): {[round(r, 1) for r in h['roe_history']]}")
    print()

    print("=== SCREENING CHECKLISTS ===")
    for name, c in result['checklists'].items():
        print(f"\n{name}: {c['score']}/{c['total']}")
        for rule, passed in c['rules'].items():
            print(f"   [{'PASS' if passed else 'FAIL'}] {rule}")
        for rule, val in c['diagnostics'].items():
            print(f"   [ -- ] {rule} = {val}")

    print()
    print("=== RELATIVE VALUATION (vs sector) ===")
    print("Percentile is the raw position of the multiple; LOWER = cheaper than peers.")
    for rv in result['relative_valuation']:
        tv = _f(rv['target'])
        mv = _f(rv['median'])
        pv = "n/a" if rv['percentile'] is None else f"{rv['percentile']:.0f}th pctile"
        print(f"   {rv['label']:10s} target={tv:>7s}   sector median={mv:>7s}   "
              f"{pv}  (n={rv['n']})")

    if result['notes']:
        print()
        print("=== NOTES / FLAGGED ===")
        for note in result['notes']:
            print(f"   {note}")


if __name__ == "__main__":
    tk = sys.argv[1] if len(sys.argv) > 1 else "MSFT"
    print_report(analyse(tk, peer_verbose=True))
