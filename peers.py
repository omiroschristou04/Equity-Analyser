"""
Peer universe module.

Given a ticker, pull its sector from yfinance, fetch a fixed list of large-cap
peers in that sector, compute a common set of metrics for each, and report where
the target sits as a percentile rank against its peers.

Metric definitions (all follow published / standard conventions — none are
invented cutoffs):

  earnings_yield   EBIT / Enterprise Value      (Greenblatt's published EY)
  roic             EBIT * (1 - tax) / Invested Capital
                   (same definition already used in analyse.py, for consistency)
  fcf_yield        (Operating Cash Flow + Capex) / Market Cap
                   Capex is reported NEGATIVE by yfinance, so it is ADDED.
                   Equity FCF yield (denominator = market cap), the dominant
                   convention. Flip DENOM_FCF to "ev" for the EV variant.
  pe               info['trailingPE']           (lower = cheaper)
  ev_ebitda        info['enterpriseToEbitda']   (lower = cheaper)
  pb               info['priceToBook']          (lower = cheaper)

yfinance traps handled here (verified live before trusting):
  - Capital Expenditure is negative -> add it to OCF, do not subtract.
  - Statement columns are newest-first, so .iloc[0] is the latest year.
  - 'Tax Rate For Calcs' is already a fraction (e.g. 0.176), not a percent.
  - Financials-sector names (banks) have NO EBIT / Capex / EV-EBITDA. Those
    metrics come back None and the ticker is dropped from that metric's
    distribution rather than faked.

DISCRETIONARY CHOICES (flagged, not published cutoffs — tell me to change any):
  - CACHE_TTL_HOURS = 24 : how stale cached fundamentals may be before refetch.
  - DENOM_FCF = "marketcap" : FCF-yield denominator (vs enterprise value).
  - Sector aggregate for medians = statistics.median (robust vs mean).
  - Percentile method = "mean" rank (percentile_of_score below).
"""

import json
import os
import statistics
import time

import yfinance as yf

CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "peer_cache.json")
# Choice, not a standard: how stale cached fundamentals may be before refetch.
CACHE_TTL_HOURS = 24
# Choice, not a standard: FCF-yield denominator ("marketcap" = equity FCF yield,
# vs "ev"). Neither is the single accepted convention.
DENOM_FCF = "marketcap"

# Fixed large-cap universes keyed by the exact sector string yfinance returns.
# ~22-30 names each. Membership is factual (sector classification), not a cutoff.
SECTOR_PEERS = {
    "Technology": [
        "AAPL", "MSFT", "NVDA", "AVGO", "ORCL", "CRM", "ADBE", "AMD", "ACN",
        "CSCO", "INTC", "TXN", "QCOM", "IBM", "INTU", "NOW", "AMAT", "MU",
        "LRCX", "ADI", "KLAC", "SNPS", "CDNS", "PANW", "CRWD",
    ],
    "Healthcare": [
        "LLY", "UNH", "JNJ", "MRK", "ABBV", "TMO", "ABT", "DHR", "PFE", "AMGN",
        "ISRG", "MDT", "BMY", "SYK", "VRTX", "GILD", "CVS", "CI", "ELV", "REGN",
        "ZTS", "BSX", "HCA", "BDX", "MCK",
    ],
    "Financial Services": [
        "BRK-B", "JPM", "V", "MA", "BAC", "WFC", "GS", "MS", "AXP", "SPGI",
        "BLK", "C", "SCHW", "CB", "MMC", "PGR", "PNC", "USB", "TFC", "AON",
        "ICE", "CME", "COF", "MET", "AIG", "TRV",
    ],
    "Consumer Cyclical": [
        "AMZN", "TSLA", "HD", "MCD", "NKE", "LOW", "SBUX", "TJX", "BKNG",
        "ORLY", "MAR", "GM", "F", "HLT", "CMG", "ROST", "YUM", "AZO", "DHI",
        "LEN", "RCL", "EBAY", "APTV", "DG", "LVS",
    ],
    "Consumer Defensive": [
        "WMT", "COST", "PG", "KO", "PEP", "PM", "MO", "MDLZ", "CL", "TGT",
        "KMB", "GIS", "SYY", "KHC", "STZ", "KR", "HSY", "KDP", "MNST", "ADM",
        "EL", "KVUE", "CHD", "MKC", "CLX",
    ],
    "Communication Services": [
        "GOOGL", "GOOG", "META", "NFLX", "DIS", "CMCSA", "VZ", "T", "TMUS",
        "CHTR", "EA", "TTWO", "WBD", "OMC", "LYV", "MTCH", "PARA", "FOXA",
        "NWSA", "IPG", "PINS", "SNAP",
    ],
    "Industrials": [
        "GE", "CAT", "RTX", "HON", "UNP", "BA", "DE", "LMT", "UPS", "ETN",
        "ADP", "GD", "NOC", "CSX", "EMR", "ITW", "FDX", "WM", "MMM", "PH",
        "TDG", "NSC", "PCAR", "CTAS", "PWR",
    ],
    "Energy": [
        "XOM", "CVX", "COP", "EOG", "SLB", "MPC", "PSX", "WMB", "OKE", "VLO",
        "HES", "OXY", "KMI", "HAL", "DVN", "FANG", "BKR", "TRGP", "CTRA",
        "EQT", "LNG", "APA", "MRO",
    ],
    "Utilities": [
        "NEE", "DUK", "SO", "D", "AEP", "SRE", "EXC", "XEL", "ED", "PEG",
        "WEC", "PCG", "ES", "EIX", "AEE", "DTE", "PPL", "FE", "ETR", "CMS",
        "CNP", "ATO", "AES",
    ],
    "Basic Materials": [
        "LIN", "SHW", "FCX", "ECL", "APD", "NEM", "CTVA", "DOW", "DD", "NUE",
        "VMC", "MLM", "PPG", "ALB", "IFF", "LYB", "STLD", "CF", "MOS", "CE",
        "EMN", "RPM",
    ],
    "Real Estate": [
        "PLD", "AMT", "EQIX", "WELL", "SPG", "PSA", "O", "CCI", "DLR", "CBRE",
        "VICI", "EXR", "AVB", "EQR", "SBAC", "VTR", "WY", "INVH", "ARE", "MAA",
        "ESS", "KIM", "UDR", "HST",
    ],
}

# Metrics where a HIGHER value is better (used only for display/interpretation).
HIGHER_IS_BETTER = {"earnings_yield", "roic", "fcf_yield"}
METRIC_KEYS = ["earnings_yield", "roic", "fcf_yield", "pe", "ev_ebitda", "pb"]


def _safe(fn):
    """Return fn() or None on any missing-field / arithmetic error."""
    try:
        v = fn()
    except Exception:
        return None
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f != f:  # NaN
        return None
    return f


def compute_metrics(ticker):
    """Fetch one ticker and compute the peer metrics plus their raw components.

    Every field is computed independently and defaults to None on failure, so a
    bank with no EBIT still yields a p/b and p/e rather than crashing the run.
    """
    s = yf.Ticker(ticker)
    info = s.info or {}
    fin = s.financials
    bs = s.balance_sheet
    cf = s.cashflow

    ebit = _safe(lambda: fin.loc["EBIT"].iloc[0])
    tax_rate = _safe(lambda: fin.loc["Tax Rate For Calcs"].iloc[0])
    invested_capital = _safe(lambda: bs.loc["Invested Capital"].iloc[0])
    ocf = _safe(lambda: cf.loc["Operating Cash Flow"].iloc[0])
    capex = _safe(lambda: cf.loc["Capital Expenditure"].iloc[0])  # negative
    market_cap = _safe(lambda: info.get("marketCap"))
    ev = _safe(lambda: info.get("enterpriseValue"))

    # Greenblatt earnings yield = EBIT / EV
    earnings_yield = None
    if ebit is not None and ev not in (None, 0):
        earnings_yield = ebit / ev

    # ROIC = NOPAT / invested capital (matches analyse.py)
    nopat = None
    roic = None
    if ebit is not None and tax_rate is not None:
        nopat = ebit * (1 - tax_rate)
        if invested_capital not in (None, 0):
            roic = nopat / invested_capital

    # FCF = OCF + capex (capex negative). FCF yield vs market cap by default.
    fcf = None
    fcf_yield = None
    if ocf is not None and capex is not None:
        fcf = ocf + capex
        denom = market_cap if DENOM_FCF == "marketcap" else ev
        if denom not in (None, 0):
            fcf_yield = fcf / denom

    pe = _safe(lambda: info.get("trailingPE"))
    ev_ebitda = _safe(lambda: info.get("enterpriseToEbitda"))
    pb = _safe(lambda: info.get("priceToBook"))

    return {
        # components (for sanity-checking)
        "ebit": ebit,
        "enterprise_value": ev,
        "tax_rate": tax_rate,
        "nopat": nopat,
        "invested_capital": invested_capital,
        "ocf": ocf,
        "capex": capex,
        "fcf": fcf,
        "market_cap": market_cap,
        # metrics
        "earnings_yield": earnings_yield,
        "roic": roic,
        "fcf_yield": fcf_yield,
        "pe": pe,
        "ev_ebitda": ev_ebitda,
        "pb": pb,
    }


def _load_cache():
    if not os.path.exists(CACHE_FILE):
        return {}
    try:
        with open(CACHE_FILE, "r") as fh:
            return json.load(fh)
    except (json.JSONDecodeError, OSError):
        return {}


def _save_cache(cache):
    try:
        with open(CACHE_FILE, "w") as fh:
            json.dump(cache, fh, indent=2)
    except OSError:
        pass


def get_metrics_cached(ticker, cache, now):
    """Return metrics for one ticker, using the cache when fresh."""
    entry = cache.get(ticker)
    if entry and (now - entry.get("_fetched", 0)) < CACHE_TTL_HOURS * 3600:
        return entry["metrics"], True
    metrics = compute_metrics(ticker)
    cache[ticker] = {"_fetched": now, "metrics": metrics}
    return metrics, False


def percentile_of_score(values, score):
    """Percentile rank of `score` within `values` (mean method), 0-100.

    (#strictly below + 0.5 * #equal) / n * 100. None values are ignored.
    Direction is raw: a low P/E gives a low percentile (i.e. cheaper than peers).
    """
    vals = [v for v in values if v is not None]
    if not vals or score is None:
        return None
    below = sum(1 for v in vals if v < score)
    equal = sum(1 for v in vals if v == score)
    # Choice, not a standard: "mean" rank (ties split half below / half at), one
    # of several percentile conventions.
    return (below + 0.5 * equal) / len(vals) * 100.0


def peer_analysis(ticker, use_cache=True, verbose=True):
    """Full peer comparison for `ticker`.

    Returns a dict with the target's metrics, every peer's metrics, the target's
    percentile rank per metric, and the sector median per metric.
    """
    tkr = ticker.upper()
    target = yf.Ticker(tkr)
    sector = (target.info or {}).get("sector")
    if sector not in SECTOR_PEERS:
        raise ValueError(
            f"No fixed peer universe for sector {sector!r} (ticker {tkr}). "
            f"Known sectors: {sorted(SECTOR_PEERS)}"
        )

    peer_tickers = SECTOR_PEERS[sector]
    cache = _load_cache() if use_cache else {}
    now = int(time.time())

    peers = {}
    hits = 0
    for t in peer_tickers:
        metrics, was_cached = get_metrics_cached(t, cache, now)
        peers[t] = metrics
        hits += int(was_cached)

    # Target metrics: reuse the peer entry if the target is in the list.
    if tkr in peers:
        target_metrics = peers[tkr]
    else:
        target_metrics, tc = get_metrics_cached(tkr, cache, now)
        hits += int(tc)

    if use_cache:
        _save_cache(cache)

    # Percentiles and medians. Population = all peer values (target included via
    # its own ticker if present; otherwise appended once). No double counting.
    percentiles = {}
    sector_median = {}
    for key in METRIC_KEYS:
        pop = [m[key] for tk, m in peers.items() if m[key] is not None]
        if tkr not in peers and target_metrics[key] is not None:
            pop = pop + [target_metrics[key]]
        percentiles[key] = percentile_of_score(pop, target_metrics[key])
        # Choice, not a standard: median (robust to outliers) as the sector
        # aggregate, rather than mean.
        sector_median[key] = statistics.median(pop) if pop else None

    result = {
        "ticker": tkr,
        "sector": sector,
        "peer_tickers": peer_tickers,
        "target": target_metrics,
        "peers": peers,
        "percentiles": percentiles,
        "sector_median": sector_median,
        "n_valid": {k: sum(1 for m in peers.values() if m[k] is not None) for k in METRIC_KEYS},
        "cache_hits": hits,
    }

    if verbose:
        _print_report(result)
    return result


def _fmt(v, pct=False, money=False):
    if v is None:
        return "n/a"
    if money:
        return f"{v:,.0f}"
    if pct:
        return f"{v*100:.2f}%"
    return f"{v:.2f}"


def _print_report(r):
    t = r["target"]
    print(f"=== PEER UNIVERSE: {r['ticker']} | sector: {r['sector']} ===")
    print(f"Peers ({len(r['peer_tickers'])}): {', '.join(r['peer_tickers'])}")
    print(f"Cache hits: {r['cache_hits']}/{len(r['peer_tickers']) + (0 if r['ticker'] in r['peers'] else 1)}")
    print()
    print("--- TARGET COMPONENTS (sanity-check these) ---")
    print(f"  EBIT:              {_fmt(t['ebit'], money=True)}")
    print(f"  Enterprise value:  {_fmt(t['enterprise_value'], money=True)}")
    print(f"  -> earnings yield: {_fmt(t['earnings_yield'], pct=True)}  (EBIT/EV)")
    print(f"  Tax rate:          {_fmt(t['tax_rate'], pct=True)}")
    print(f"  NOPAT:             {_fmt(t['nopat'], money=True)}")
    print(f"  Invested capital:  {_fmt(t['invested_capital'], money=True)}")
    print(f"  -> ROIC:           {_fmt(t['roic'], pct=True)}")
    print(f"  Operating CF:      {_fmt(t['ocf'], money=True)}")
    print(f"  Capex (neg):       {_fmt(t['capex'], money=True)}")
    print(f"  FCF (OCF+capex):   {_fmt(t['fcf'], money=True)}")
    print(f"  Market cap:        {_fmt(t['market_cap'], money=True)}")
    print(f"  -> FCF yield:      {_fmt(t['fcf_yield'], pct=True)}  (FCF/{DENOM_FCF})")
    print(f"  P/E:               {_fmt(t['pe'])}")
    print(f"  EV/EBITDA:         {_fmt(t['ev_ebitda'])}")
    print(f"  P/B:               {_fmt(t['pb'])}")
    print()
    print("--- PERCENTILE vs SECTOR (higher% = higher raw value) ---")
    for k in METRIC_KEYS:
        arrow = "higher=better" if k in HIGHER_IS_BETTER else "lower=cheaper"
        p = r["percentiles"][k]
        med = r["sector_median"][k]
        n = r["n_valid"][k]
        med_s = _fmt(med, pct=(k in HIGHER_IS_BETTER))
        val = t[k]
        val_s = _fmt(val, pct=(k in HIGHER_IS_BETTER))
        p_s = "n/a" if p is None else f"{p:5.1f}"
        print(f"  {k:14s} target={val_s:>9s}  median={med_s:>9s}  pctile={p_s}  (n={n:2d}, {arrow})")
    print()


if __name__ == "__main__":
    import sys
    tk = sys.argv[1] if len(sys.argv) > 1 else "MSFT"
    peer_analysis(tk)
