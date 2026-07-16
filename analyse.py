import sys
import statistics
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

TICKER = sys.argv[1].upper() if len(sys.argv) > 1 else "MSFT"

stock = yf.Ticker(TICKER)
info = stock.info

# Fail fast on out-of-scope sectors. This tool's core (enterprise value, capex,
# unlevered FCF, ROIC vs WACC) is undefined for banks and REITs, so exit rather
# than emit a NaN-filled, misleading report.
if info.get('sector') in ('Financial Services', 'Real Estate'):
    print(
        "This tool does not cover financials or REITs. Banks have no meaningful\n"
        "enterprise value, capex, or unlevered free cash flow — debt is raw material,\n"
        "not financing. They are valued on P/B against ROTE, or via a dividend\n"
        "discount model. That is a different framework, not a variant of this one."
    )
    sys.exit(0)

fin = stock.financials
bs = stock.balance_sheet
cf = stock.cashflow

# yfinance pads shorter histories with a trailing NaN year (e.g. KO's income
# statement has 5 columns but only 4 real years). Drop NaNs (NaN != NaN) so they
# don't poison zip/stdev/comparisons downstream. Series stay newest-first.
def _clean(series):
    return [x for x in series if x == x]


net_income = _clean(fin.loc['Net Income'])
equity = _clean(bs.loc['Stockholders Equity'])
revenue = _clean(fin.loc['Total Revenue'])
ocf = _clean(cf.loc['Operating Cash Flow'])
capex = _clean(cf.loc['Capital Expenditure'])

roe_history = [n / e * 100 for n, e in zip(net_income, equity)]
fcf_history = [o + c for o, c in zip(ocf, capex)]
revenue_growth = [
    (revenue[i] / revenue[i + 1] - 1) * 100 for i in range(len(revenue) - 1)
]

debt_to_equity = info['debtToEquity'] / 100
wacc = calculate_wacc(TICKER)['wacc']

ebit = fin.loc['EBIT'].iloc[0]
tax_rate = fin.loc['Tax Rate For Calcs'].iloc[0]
invested_capital = bs.loc['Invested Capital'].iloc[0]
roic = ebit * (1 - tax_rate) / invested_capital

share_count_history = _clean(bs.loc['Ordinary Shares Number'])

hist = stock.history(period="1y")
price = hist['Close'].iloc[-1]
ma_200 = hist['Close'].rolling(200).mean().iloc[-1]
worst_day = hist['Close'].pct_change().idxmin()
volume_spike_on_decline = (
    hist.loc[worst_day, 'Volume'] > hist['Volume'].mean() * 1.5
)

try:
    inventory = list(bs.loc['Inventory'])
    inventory_growth = (inventory[0] / inventory[1] - 1) * 100
except KeyError:
    inventory_growth = 0.0

# --- Peer universe (sector-relative metrics) ---
# Prints its own component breakdown so the percentiles below are checkable.
peer = peer_analysis(TICKER, verbose=True)
pct = peer['percentiles']
sector_median = peer['sector_median']
target_fcf_yield = peer['target']['fcf_yield']
sector_fcf_yield = sector_median['fcf_yield']

# 12-1 month momentum: return from ~12 months ago to ~1 month ago (skip the most
# recent ~21 trading days), the standard cross-sectional momentum window.
closes = hist['Close']
if len(closes) > 22:
    momentum_12_1 = float((closes.iloc[-22] / closes.iloc[0] - 1) * 100)
else:
    momentum_12_1 = float((closes.iloc[-1] / closes.iloc[0] - 1) * 100)

results = {}
results['Buffett quality'] = buffett_quality(
    roe_history, debt_to_equity, fcf_history
)
results['Lynch GARP'] = lynch_garp(
    info['trailingPegRatio'],
    info['earningsGrowth'] * 100,
    inventory_growth,
    info['revenueGrowth'] * 100,
)
results['Graham value'] = graham_value(
    info['priceToBook'], info['currentRatio'], net_income
)
results['Goldberg technical'] = goldberg_technical(
    price, ma_200, volume_spike_on_decline
)
results['Bajaj compounder'] = bajaj_compounder(
    revenue_growth, roe_history, roic * 100, wacc * 100, share_count_history
)

# Newly wired via the peer universe. Thresholds live inside criteria.py
# (top-quartile = 75, momentum > 0); we only supply the measured inputs.
skipped = []
greenblatt_combined_rank = None
if pct['earnings_yield'] is not None and pct['roic'] is not None:
    results['Greenblatt magic'], greenblatt_combined_rank = greenblatt_magic(
        pct['earnings_yield'], pct['roic']
    )
else:
    skipped.append(
        "Greenblatt magic - needs EY & ROIC percentiles; unavailable for "
        f"{peer['sector']} (EY pctile={pct['earnings_yield']}, "
        f"ROIC pctile={pct['roic']})."
    )

if target_fcf_yield is not None and sector_fcf_yield is not None:
    results['Inglis-Jones / Gleave'] = inglis_jones_gleave(
        target_fcf_yield, sector_fcf_yield, momentum_12_1
    )
else:
    skipped.append(
        "Inglis-Jones / Gleave - needs FCF yields; unavailable for "
        f"{peer['sector']} (target={target_fcf_yield}, sector={sector_fcf_yield})."
    )

print(f"=== {info['longName']} ({TICKER}) ===")
print(f"Sector: {info['sector']}")
print(f"Price: {price:.2f}   200d MA: {ma_200:.2f}")
print(f"WACC: {wacc:.2%}   ROIC: {roic:.2%}")
print(f"12-1 momentum: {momentum_12_1:+.1f}%   (feeds Inglis-Jones positive_momentum)")
print(f"ROE (newest first): {[round(r, 1) for r in roe_history]}")
print()

print("=== SCREENING CHECKLISTS ===")
for name, checks in results.items():
    score = checks.pop('score')
    total = len(checks)
    print(f"\n{name}: {score}/{total}")
    for rule, passed in checks.items():
        mark = "PASS" if passed else "FAIL"
        print(f"   [{mark}] {rule}")
    if name == 'Greenblatt magic' and greenblatt_combined_rank is not None:
        # Diagnostic, not a pass/fail rule -- returned separately by criteria.py.
        print(f"   [ -- ] combined_rank = {greenblatt_combined_rank}")

print()
print("=== RELATIVE VALUATION (vs sector) ===")
print("Percentile is the raw position of the multiple; LOWER = cheaper than peers.")
for key, label in [('pe', 'P/E'), ('ev_ebitda', 'EV/EBITDA'), ('pb', 'P/B')]:
    target_val = peer['target'][key]
    med = sector_median[key]
    p = pct[key]
    n = peer['n_valid'][key]
    tv = "n/a" if target_val is None else f"{target_val:.2f}"
    mv = "n/a" if med is None else f"{med:.2f}"
    pv = "n/a" if p is None else f"{p:.0f}th pctile"
    print(f"   {label:10s} target={tv:>7s}   sector median={mv:>7s}   {pv}  (n={n})")

if skipped:
    print()
    print("=== FLAGGED / NOT RUN ===")
    for msg in skipped:
        print(f"   {msg}")