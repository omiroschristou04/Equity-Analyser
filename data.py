import yfinance as yf
from criteria import buffett_quality

stock = yf.Ticker("MSFT")

net_income = list(stock.financials.loc['Net Income'])
equity = list(stock.balance_sheet.loc['Stockholders Equity'])
ocf = list(stock.cashflow.loc['Operating Cash Flow'])
capex = list(stock.cashflow.loc['Capital Expenditure'])

roe_history = [n / e * 100 for n, e in zip(net_income, equity)]
fcf_history = [o + c for o, c in zip(ocf, capex)]
debt_to_equity = stock.info['debtToEquity'] / 100

result = buffett_quality(roe_history, debt_to_equity, fcf_history)
print(result)
print(roe_history)
print(fcf_history)
print(debt_to_equity)