import yfinance as yf
from wacc import calculate_wacc

TICKER = "MSFT"
TERMINAL_GROWTH = 0.025
STAGE1_YEARS = 5
FADE_YEARS = 5

stock = yf.Ticker(TICKER)
info = stock.info

ebit = stock.financials.loc['EBIT'].iloc[0]
tax_rate = stock.financials.loc['Tax Rate For Calcs'].iloc[0]
d_and_a = stock.cashflow.loc['Depreciation And Amortization'].iloc[0]
capex_reported = stock.cashflow.loc['Capital Expenditure'].iloc[0]
delta_nwc = stock.cashflow.loc['Change In Working Capital'].mean()

nopat = ebit * (1 - tax_rate)
maintenance_capex = -d_and_a
base_fcf = nopat + d_and_a + maintenance_capex + delta_nwc

wacc = calculate_wacc(TICKER)['wacc']
net_debt = stock.balance_sheet.loc['Net Debt'].iloc[0]
shares = stock.balance_sheet.loc['Ordinary Shares Number'].iloc[0]
current_price = info['currentPrice']

revenue = list(stock.financials.loc['Total Revenue'])
years_of_data = len(revenue) - 1
hist_rev_cagr = (revenue[0] / revenue[-1]) ** (1 / years_of_data) - 1


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
    return equity / shares, discounted_tv / ev


print(f"{TICKER} reverse DCF")
print(f"Reported capex: {capex_reported:,.0f}")
print(f"D&A (maintenance proxy): {-d_and_a:,.0f}")
print(f"Avg delta NWC: {delta_nwc:,.0f}")
print(f"Normalised base FCF: {base_fcf:,.0f}")
print(f"WACC: {wacc:.2%}")
print(f"Terminal growth: {TERMINAL_GROWTH:.1%}")
print(f"Structure: {STAGE1_YEARS}yr growth, {FADE_YEARS}yr fade, then terminal")
print(f"Historical revenue CAGR: {hist_rev_cagr:.1%}")
print(f"Current price: {current_price:.2f}")
print()

implied = None
print("Growth  ->  Value/share   TV% of EV")
for i in range(2, 31):
    g = i / 100
    v, tv_share = value_at_growth(g)
    marker = ""
    if abs(v - current_price) < current_price * 0.02:
        marker = "  <-- market"
        implied = (g, tv_share)
    print(f"{g:>5.0%}  ->  {v:9.2f}     {tv_share:5.0%}{marker}")

print()
if implied:
    g, tv_share = implied
    print(f"IMPLIED 5YR FCF GROWTH: {g:.0%}")
    print(f"Historical revenue CAGR: {hist_rev_cagr:.1%}")
    if g > hist_rev_cagr * 1.5:
        print("FLAG: implied growth far exceeds historical revenue growth.")
        print("      Model cannot value this name credibly. Treat output as diagnostic.")
    if tv_share > 0.75:
        print(f"FLAG: terminal value is {tv_share:.0%} of EV.")
        print("      You are valuing an assumption, not cash flows.")
else:
    print("No growth rate in range matches the market price.")
    print("FLAG: model cannot reconcile to price. Check the base.")