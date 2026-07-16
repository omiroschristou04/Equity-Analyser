import yfinance as yf
from wacc import calculate_wacc

TICKER = "MSFT"
GROWTH_RATE = 0.08
TERMINAL_GROWTH = 0.025
YEARS = 5

stock = yf.Ticker(TICKER)
info = stock.info

ebit = stock.financials.loc['EBIT'].iloc[0]
tax_rate = stock.financials.loc['Tax Rate For Calcs'].iloc[0]
d_and_a = stock.cashflow.loc['Depreciation And Amortization'].iloc[0]
capex = stock.cashflow.loc['Capital Expenditure'].iloc[0]
delta_nwc = stock.cashflow.loc['Change In Working Capital'].iloc[0]

base_fcf = ebit * (1 - tax_rate) + d_and_a + capex + delta_nwc

wacc = calculate_wacc(TICKER)['wacc']

projected = [base_fcf * (1 + GROWTH_RATE) ** y for y in range(1, YEARS + 1)]
discounted = [f / (1 + wacc) ** y for y, f in enumerate(projected, start=1)]

terminal_value = projected[-1] * (1 + TERMINAL_GROWTH) / (wacc - TERMINAL_GROWTH)
discounted_tv = terminal_value / (1 + wacc) ** YEARS

enterprise_value = sum(discounted) + discounted_tv

net_debt = stock.balance_sheet.loc['Net Debt'].iloc[0]
equity_value = enterprise_value - net_debt

shares = stock.balance_sheet.loc['Ordinary Shares Number'].iloc[0]
value_per_share = equity_value / shares

current_price = info['currentPrice']
upside = (value_per_share / current_price - 1) * 100

print(f"Base unlevered FCF: {base_fcf:,.0f}")
print(f"WACC: {wacc:.2%}")
print(f"Enterprise value: {enterprise_value:,.0f}")
print(f"Equity value: {equity_value:,.0f}")
print(f"Value per share: {value_per_share:.2f}")
print(f"Current price: {current_price:.2f}")
print(f"Upside/downside: {upside:+.1f}%")