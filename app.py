"""Streamlit front end wrapping analyse.py and reverse_dcf.py.

Run with:  streamlit run app.py
"""
import pandas as pd
import streamlit as st

from analyse import analyse
from reverse_dcf import reverse_dcf

st.set_page_config(page_title="Equity Analyser", layout="wide")


def fmt(v, pct=False, money=False, dp=2):
    """None/NaN-safe formatter."""
    if v is None or v != v:
        return "n/a"
    if money:
        return f"{v:,.0f}"
    if pct:
        return f"{v * 100:.{dp}f}%"
    return f"{v:,.{dp}f}"


def render_header(result):
    h = result['header']
    st.subheader(f"{h['long_name']} ({result['ticker']})")
    st.caption(f"Sector: {h['sector']}")
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Price", fmt(h['price']))
    c2.metric("200d MA", fmt(h['ma_200']))
    c3.metric("WACC", fmt(h['wacc'], pct=True))
    c4.metric("ROIC", fmt(h['roic'], pct=True))
    mom = h['momentum_12_1']
    c5.metric("12-1 momentum", "n/a" if mom is None else f"{mom:.1f}%")
    if result.get('notes'):
        for note in result['notes']:
            st.caption(f"ℹ️ {note}")


def render_reverse_dcf(ticker):
    st.markdown("### Reverse DCF — growth implied by the market price")
    rd = reverse_dcf(ticker)

    if rd.get('error'):
        st.warning(rd['error'])
        return
    if not rd.get('rows'):
        st.warning("Reverse DCF could not be computed.")
        return

    # Plausibility flags, shown prominently first.
    if rd['reconciled']:
        st.success(f"**Implied 5yr FCF growth: {rd['implied_growth']:.0%}** "
                   f"(terminal value = {fmt(rd['implied_tv_share'], pct=True, dp=0)} of EV)")
    for flag in rd['flags']:
        st.error(f"⚠️ {flag}")

    a1, a2, a3, a4 = st.columns(4)
    a1.metric("Base FCF", fmt(rd.get('base_fcf'), money=True))
    a2.metric("WACC", fmt(rd.get('wacc'), pct=True))
    a3.metric("Terminal growth", fmt(rd.get('terminal_growth'), pct=True, dp=1))
    a4.metric("Hist. revenue CAGR", fmt(rd.get('hist_rev_cagr'), pct=True, dp=1))
    st.caption(f"Current price: {fmt(rd.get('current_price'))}  ·  "
               f"structure: {rd['stage1_years']}yr growth, {rd['fade_years']}yr fade, "
               f"then {fmt(rd['terminal_growth'], pct=True, dp=1)} terminal")

    rows = rd['rows']
    df = pd.DataFrame([{
        "Growth": f"{r['growth']:.0%}",
        "Value / share": round(r['value'], 2),
        "TV % of EV": "n/a" if r['tv_share'] != r['tv_share'] else f"{r['tv_share'] * 100:.0f}%",
    } for r in rows])
    market_idx = {i for i, r in enumerate(rows) if r['is_market']}

    def highlight(s):
        hit = s.name in market_idx
        return ['background-color: #ffe08a; font-weight: 700' if hit else '' for _ in s]

    try:
        # Colour-highlight the implied-growth row (needs jinja2, shipped with Streamlit).
        st.dataframe(df.style.apply(highlight, axis=1),
                     use_container_width=True, height=560, hide_index=True)
    except Exception:
        # Fallback if the Styler backend is unavailable: explicit marker column.
        df.insert(0, "", ["◄" if i in market_idx else "" for i in range(len(df))])
        st.dataframe(df, use_container_width=True, height=560, hide_index=True)
    if market_idx:
        st.caption("Highlighted row = growth rate whose intrinsic value matches "
                   "today's price (within 2%).")


def render_relative_valuation(result):
    st.markdown("### Relative valuation vs sector")
    st.caption("Percentile is the raw position of the multiple among peers — "
               "**lower = cheaper** than the sector.")
    rows = []
    for rv in result['relative_valuation']:
        rows.append({
            "Multiple": rv['label'],
            "Target": fmt(rv['target']),
            "Sector median": fmt(rv['median']),
            "Percentile": "n/a" if rv['percentile'] is None else f"{rv['percentile']:.0f}",
            "Peers (n)": rv['n'],
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def render_checklists(result):
    st.markdown("### Screening checklists")
    items = list(result['checklists'].items())
    cols = st.columns(2)
    for idx, (name, c) in enumerate(items):
        with cols[idx % 2]:
            st.markdown(f"**{name} — {c['score']}/{c['total']}**")
            for rule, passed in c['rules'].items():
                st.markdown(f"{'✅' if passed else '❌'} {rule}")
            for rule, val in c['diagnostics'].items():
                shown = round(val, 1) if isinstance(val, (int, float)) else val
                st.markdown(f"➖ {rule} = {shown}")
            st.write("")


# --- Page ---
st.title("Equity Analyser")
st.caption("Multi-method valuation for non-financial equities. "
           "Financials and REITs are out of scope.")

ticker = st.text_input("Ticker", value="MSFT").strip().upper()
run = st.button("Run", type="primary")

if run:
    if not ticker:
        st.warning("Enter a ticker.")
    else:
        try:
            with st.spinner(f"Analysing {ticker} and its peer universe…"):
                result = analyse(ticker)
            if result.get('out_of_scope'):
                st.info(result['scope_message'])
            else:
                render_header(result)
                st.divider()
                render_reverse_dcf(ticker)
                st.divider()
                render_relative_valuation(result)
                st.divider()
                render_checklists(result)
        except Exception as exc:
            # Never surface a stack trace — just the ticker and the reason.
            st.error(f"Could not analyse **{ticker}**: {exc.__class__.__name__}: {exc}")
