"""Streamlit shell for the equity report.

Streamlit's only job is the hero, the ticker input and the Run button; the
report itself is a single self-contained HTML document built by report.py and
rendered in one iframe via st.iframe (height="content" auto-fits the srcdoc).
"""
import datetime

import streamlit as st

from report import build_report_html, CSS, FONT_LINK

st.set_page_config(
    page_title="Equity Analyser — Reverse DCF valuation",
    page_icon="📊",
    layout="wide",
)

# Hero-only additions to the imported house CSS (three-across cards that collapse
# to one column on narrow screens). The house style itself is reused, not copied.
HERO_EXTRA_CSS = """
.hero-cards{display:grid;grid-template-columns:repeat(3,1fr);gap:18px;}
.hero-cards .card{margin-bottom:0;}
.hero-body{font-size:14px;color:#334155;margin:0;line-height:1.5;}
@media (max-width:640px){.hero-cards{grid-template-columns:1fr;}}
"""

HERO_BODY = """
<div class="topbar"></div>
<div class="masthead">
  <div class="inner">
    <div>
      <h1>Equity Analyser</h1>
      <div class="sub" style="font-size:15px;">What growth rate does the market price imply?</div>
    </div>
    <div class="right">
      <div class="status-lbl">Built by</div>
      <div style="color:#fff;font-size:15px;font-weight:600;margin-top:6px;">Omiros Christou</div>
      <div style="color:#cbd5e1;font-size:12px;margin-top:4px;">BSc Finance &amp; Actuarial Science</div>
      <div style="color:#cbd5e1;font-size:12px;">Bayes Business School, City, University of London</div>
    </div>
  </div>
</div>
<div class="wrap" style="padding-top:24px;padding-bottom:24px;">
  <div class="hero-cards">
    <div class="card"><h2>Reverse DCF</h2>
      <p class="hero-body">Solves for the growth rate today's price already assumes,
      then tests it against what the business has delivered.</p></div>
    <div class="card"><h2>Seven screening frameworks</h2>
      <p class="hero-body">Codified from published criteria. They are designed to
      disagree; the disagreement is the output.</p></div>
    <div class="card"><h2>Model limits, stated</h2>
      <p class="hero-body">Flags when implied growth outruns history or terminal
      value dominates enterprise value.</p></div>
  </div>
</div>"""


def _hero_html():
    return (f'<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">'
            f'{FONT_LINK}<style>{CSS}{HERO_EXTRA_CSS}</style></head>'
            f'<body>{HERO_BODY}</body></html>')


st.iframe(_hero_html(), height="content")

st.caption("Enter a ticker and press Run. Financials and REITs are out of scope.")
ticker = st.text_input("Ticker", value="MSFT").strip().upper()

if st.button("Run", type="primary"):
    if not ticker:
        st.warning("Enter a ticker.")
    else:
        try:
            with st.spinner(f"Building report for {ticker}…"):
                html_doc = build_report_html(ticker)
            st.iframe(html_doc, height="content")
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
