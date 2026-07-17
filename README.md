# Equity Analyser
**[▶ Live app](https://equity-analyseromiroschristou.streamlit.app/)**
Multi-method valuation tool for individual equities. Input a ticker, get a structured research report.

## Why

I run a personal equity portfolio using discounted cash flow analysis and manual
screening. This automates the repetitive parts of that process — pulling
fundamentals, computing ratios, running the DCF, testing the stock against
published screening rules — so the time goes on the judgement call rather than
the arithmetic.

## Method

Four independent lenses, because no single method is reliable alone:

1. **DCF** — projects free cash flow, discounts at WACC, outputs an intrinsic
   value estimate with a sensitivity table across WACC and terminal growth.
2. **Relative valuation** — P/E, EV/EBITDA, P/B against sector medians. Catches
   names where the DCF assumptions are doing too much work.
3. **Quality** — ROIC vs WACC spread, margin trend, leverage trajectory, FCF
   conversion. Whether the business is good, not just cheap.
4. **Momentum** — 12-1 month return, position vs 50/200-day moving averages.
   Cheap and improving is a different trade from cheap and falling.

Where these disagree is the interesting part. The tool reports the disagreement
rather than averaging it away.

## Screening checklists

The stock is tested against seven rules-based frameworks. Each returns pass/fail
per criterion plus an aggregate score:

- **Buffett-style quality** — sustained ROE, low leverage, consistent FCF
- **Lynch GARP** — PEG, earnings growth band, inventory vs sales
- **Greenblatt Magic Formula** — earnings yield and ROIC as sector percentile
  ranks against the peer universe
- **Graham deep value** — P/B, current ratio, earnings consistency
- **Goldberg technical health** — 200-day MA position, overextension flag,
  volume-confirmed declines
- **Inglis-Jones / Gleave** — FCF yield above the sector median, with 12-1
  momentum confirmation
- **Bajaj compounder test** — multi-year growth durability, ROIC above WACC,
  dilution check

All seven run. Greenblatt and Inglis-Jones / Gleave are sector-relative: they
draw earnings-yield / ROIC percentiles and the sector FCF yield from a peer
universe (`peers.py`). That peer universe is a **fixed large-cap list per
sector**, cached locally — a comparison set, not a full sector screen.

These are codified from published criteria and from *Stock Market Maestros*
(2024). The tool tests whether a stock meets stated rules. It does not claim to
reproduce anyone's judgement.

## Output

- Intrinsic value estimate and **upside/downside vs current price**, with
  sensitivity ranges
- Relative valuation position vs sector
- Quality and momentum scores
- Checklist results, one line per framework
- A written synthesis weighing the conflicting signals

The output is a valuation gap, not a price forecast. The DCF says what the cash
flows are worth under stated assumptions. It says nothing about when, or
whether, the market closes the gap — that needs a catalyst and a horizon, which
sit outside the model.

## Known limitations

The DCF is sensitive to the base year. Two distortions found in testing:

- **One-off working capital swings.** A single year's change in working capital, compounded and capitalised, can move implied growth by more than 10 percentage points. Mitigated by averaging across available years.
- **Investment cycles.** Reported capex at a company mid-build reflects growth spend, not maintenance. Stripping it from the base while also demanding the growth it funds double-penalises the company. The base uses D&A as a maintenance proxy.

The model flags when implied growth exceeds historical revenue growth by more than 50%, and when terminal value exceeds 75% of enterprise value. In both cases the output is a diagnostic, not a valuation.

**Non-financial equities only.** The core measures — enterprise value, capex, unlevered free cash flow, ROIC vs WACC — are undefined for banks and REITs, where debt is raw material rather than financing. Financials and Real Estate are explicitly out of scope: the tool exits with an explanation rather than producing a NaN-filled, misleading report. Those names need a different framework (P/B against ROTE, or a dividend discount model).
## Status

In development.

## Stack

Python — pandas, numpy, yfinance, matplotlib.

