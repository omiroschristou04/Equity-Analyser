"""Streamlit shell for the equity report.

Streamlit's only job is the ticker input and the Run button; the entire report
is a single self-contained HTML document built by report.py and rendered in one
iframe via st.components.v1.html.
"""
import datetime

import streamlit as st
import streamlit.components.v1 as components

from report import build_report_html

st.set_page_config(page_title="Equity Analyser", layout="wide")
st.title("Equity Analyser")
st.caption("Enter a ticker and press Run. Financials and REITs are out of scope.")

ticker = st.text_input("Ticker", value="MSFT").strip().upper()

if st.button("Run", type="primary"):
    if not ticker:
        st.warning("Enter a ticker.")
    else:
        try:
            with st.spinner(f"Building report for {ticker}…"):
                html_doc = build_report_html(ticker)
            components.html(html_doc, height=3200, scrolling=True)
            # The document is fully self-contained (inline base64 chart), so the
            # downloaded file opens offline; only the Google font degrades.
            date = datetime.datetime.now().strftime("%Y%m%d")
            st.download_button(
                label="Download report",
                data=html_doc,
                file_name=f"{ticker}_{date}.html",
                mime="text/html",
            )
        except Exception as exc:
            # Never surface a stack trace — just the ticker and the reason.
            st.error(f"Could not generate report for {ticker}: "
                     f"{exc.__class__.__name__}: {exc}")
