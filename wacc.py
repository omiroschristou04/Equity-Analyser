import yfinance as yf


def calculate_wacc(ticker, risk_free_rate=0.042, market_risk_premium=0.055):
    """
    Re via CAPM: Rf + beta * MRP
    Rd from reported interest expense over total debt
    Weights at market value of equity, book value of debt
    """
    stock = yf.Ticker(ticker)
    info = stock.info

    beta = info['beta']
    cost_of_equity = risk_free_rate + beta * market_risk_premium

    interest_expense = stock.financials.loc['Interest Expense'].iloc[0]
    total_debt = stock.balance_sheet.loc['Total Debt'].iloc[0]
    cost_of_debt = interest_expense / total_debt

    tax_rate = stock.financials.loc['Tax Rate For Calcs'].iloc[0]

    equity_value = info['marketCap']
    debt_value = total_debt
    total_capital = equity_value + debt_value

    wacc = (
        (equity_value / total_capital) * cost_of_equity
        + (debt_value / total_capital) * cost_of_debt * (1 - tax_rate)
    )

    return {
        'cost_of_equity': cost_of_equity,
        'cost_of_debt': cost_of_debt,
        'tax_rate': tax_rate,
        'equity_weight': equity_value / total_capital,
        'debt_weight': debt_value / total_capital,
        'wacc': wacc,
    }


if __name__ == "__main__":
    print(calculate_wacc("MSFT"))