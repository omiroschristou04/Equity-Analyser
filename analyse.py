import statistics
import yfinance as yf
from wacc import calculate_wacc
from criteria import (
    buffett_quality,
    lynch_garp,
    graham_value,
    goldberg_technical,
    bajaj_compounder,
)

TICKER = "MSFT"

stock = yf.Ticker(TICKER)
info = stock.info
fin = stock.financials
bs = stock.balance_sheet
cf = stock.cashflow

net_income = list(fin.loc['Net Income'])
equity = list(bs.loc['Stockholders Equity'])
revenue = list(fin.loc['Total Revenue'])
ocf = list(cf.loc['Operating Cash Flow'])
capex = list(cf.loc['Capital Expenditure'])

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

share_count_history = list(bs.loc['Ordinary Shares Number'])

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

print(f"=== {info['longName']} ({TICKER}) ===")
print(f"Sector: {info['sector']}")
print(f"Price: {price:.2f}   200d MA: {ma_200:.2f}")
print(f"WACC: {wacc:.2%}   ROIC: {roic:.2%}")
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

print()
print("=== NOT RUN ===")
print("Greenblatt magic formula  - needs sector percentile ranks")
print("Inglis-Jones / Gleave     - needs sector FCF yield")
print("Both require a peer universe. Phase 2.")