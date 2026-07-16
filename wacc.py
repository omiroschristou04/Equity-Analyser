import yfinance as yf


def _row0(df, name):
    """Latest value of a statement row, or None if the row is absent."""
    try:
        v = df.loc[name].iloc[0]
        return float(v) if v == v else None  # NaN -> None
    except Exception:
        return None


def calculate_wacc(ticker, risk_free_rate=0.042, market_risk_premium=0.055):
    """
    Re via CAPM: Rf + beta * MRP
    Rd from reported interest expense over total debt
    Weights at market value of equity, book value of debt

    Robust to missing data:
      - No 'Interest Expense'/'Total Debt' row (net-cash firms, e.g. ARM) -> the
        debt term drops out (cost_of_debt = 0, debt weight = 0).
      - Missing beta (very recent listings) -> falls back to 1.0 and sets
        beta_assumed=True so the caller can flag it. 1.0 is the market-average
        beta, a data-absence fallback, not a tuned input.
    """
    stock = yf.Ticker(ticker)
    info = stock.info or {}
    fin = stock.financials
    bs = stock.balance_sheet

    beta = info.get('beta')
    beta_assumed = beta is None
    if beta_assumed:
        beta = 1.0
    cost_of_equity = risk_free_rate + beta * market_risk_premium

    interest_expense = _row0(fin, 'Interest Expense') or 0.0
    total_debt = _row0(bs, 'Total Debt') or 0.0
    cost_of_debt = interest_expense / total_debt if total_debt else 0.0

    tax_rate = _row0(fin, 'Tax Rate For Calcs')
    if tax_rate is None:
        tax_rate = 0.0

    equity_value = info.get('marketCap') or 0.0
    debt_value = total_debt
    total_capital = equity_value + debt_value

    if total_capital == 0:
        # Nothing to weight on; report cost of equity as the discount rate.
        equity_weight, debt_weight, wacc = 1.0, 0.0, cost_of_equity
    else:
        equity_weight = equity_value / total_capital
        debt_weight = debt_value / total_capital
        wacc = (
            equity_weight * cost_of_equity
            + debt_weight * cost_of_debt * (1 - tax_rate)
        )

    return {
        'cost_of_equity': cost_of_equity,
        'cost_of_debt': cost_of_debt,
        'tax_rate': tax_rate,
        'equity_weight': equity_weight,
        'debt_weight': debt_weight,
        'wacc': wacc,
        'beta_assumed': beta_assumed,
    }


if __name__ == "__main__":
    import sys
    print(calculate_wacc(sys.argv[1] if len(sys.argv) > 1 else "MSFT"))
