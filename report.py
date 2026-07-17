"""Self-contained HTML equity report, styled to match the daily market briefing.

Presentation only — every number comes from analyse.py / reverse_dcf.py
unchanged. build_report_html(ticker) returns a complete HTML document string
(price chart embedded as an inline base64 PNG, so the file has no external
assets beyond the Google-hosted Inter font).
"""
import base64
import datetime
import html
import io

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402
import yfinance as yf  # noqa: E402

from analyse import analyse  # noqa: E402
from reverse_dcf import reverse_dcf  # noqa: E402

# House palette (from reference_report.html).
NAVY, POS, NEG, AMBER = '#0a1628', '#16a34a', '#dc2626', '#d97706'

EXPLANATIONS = {
    "kpi": (
        "Five numbers frame everything below. Price against the 200-day moving "
        "average gives trend context — a stock below its long-term average is "
        "being repriced, and the question is whether fundamentals justify it. "
        "WACC is the blended cost of the capital funding the business; ROIC is "
        "what the business earns on that capital. The spread between them is "
        "where value is created or destroyed. Momentum tells you which way the "
        "market is currently voting."
    ),
    "chart": (
        "The 50-day average tracks the recent trend, the 200-day the long-term "
        "one. Price relative to both, and the two relative to each other, show "
        "whether a move is noise or a change in regime. Valuation says what "
        "something is worth; the chart says what the market is doing about it. "
        "The two disagreeing is normal — and is usually where the interesting "
        "questions are."
    ),
    "reverse_dcf": (
        "A discounted cash flow tells you what a company's cash flows are worth "
        "under stated assumptions — it does not forecast the price. Running it "
        "backwards is more useful: instead of asking what the business is "
        "worth, it asks what growth rate today's price already assumes. That "
        "number is testable against history. If the market implies growth far "
        "above what the company has ever delivered, the burden of proof sits "
        "with the bulls. What the model cannot say is when, or whether, the "
        "gap closes — that requires a catalyst and a horizon, both outside "
        "the maths."
    ),
    "base_fcf": (
        "The base year is the single most sensitive input: every error in it "
        "is compounded for a decade and capitalised into the terminal value at "
        "roughly thirty times. Two distortions dominate. One-off working "
        "capital swings — a tax payment, an inventory build — masquerade as "
        "recurring cash costs, so the model averages working capital across "
        "available years. And reported capex at a company mid-investment-cycle "
        "reflects growth spending, not maintenance; stripping it out while "
        "also demanding the growth it funds penalises the company twice. The "
        "base therefore uses depreciation as a maintenance-capex proxy — a "
        "choice, and one that assumes the investment cycle eventually reverts."
    ),
    "terminal_value": (
        "Terminal value is everything after the explicit forecast, compressed "
        "into one number by a perpetual-growth assumption. When it exceeds "
        "roughly three-quarters of enterprise value, the valuation no longer "
        "rests on cash flows anyone has projected — it rests on the "
        "assumption itself. The model flags that condition rather than hiding "
        "it, because a DCF that is 85% terminal value is an opinion wearing "
        "the costume of a calculation."
    ),
    "relative_valuation": (
        "Multiples against sector peers catch what an intrinsic model can "
        "miss: a stock can look cheap on a DCF because the assumptions are "
        "doing too much work, while still trading rich against every "
        "comparable business. Percentile position matters more than the raw "
        "multiple — 25x earnings is expensive in one sector and cheap in "
        "another. Where the DCF and the relative view disagree, one set of "
        "assumptions is wrong, and finding out which is the analysis."
    ),
    "checklists": (
        "Seven rules-based frameworks codified from published criteria — "
        "Buffett-style quality, Lynch's GARP, Graham's deep value, "
        "Greenblatt's ranking, and three drawn from practitioner interviews "
        "in Stock Market Maestros. Each tests stated, computable rules; none "
        "simulates anyone's judgement. They are designed to disagree: a stock "
        "passing quality screens while failing value screens is a category — "
        "a good business at a demanding price — and that disagreement is the "
        "output, not an error to be averaged away."
    ),
    "momentum": (
        "Momentum is measured over twelve months excluding the most recent — "
        "the standard construction, because the last month tends to reverse. "
        "Its role here is confirmation: cheap and rising is a value "
        "opportunity, cheap and falling is a falling knife, and the "
        "difference is the timing risk a pure valuation model cannot see. "
        "One framework in the checklist requires cash-flow strength and "
        "positive momentum together for exactly this reason — either alone "
        "is insufficient."
    ),
    "methodology": (
        "This tool covers non-financial equities only. Banks and insurers "
        "have no meaningful enterprise value, capex, or unlevered free cash "
        "flow — debt is their raw material, not their financing — and are "
        "valued on book value against returns on tangible equity, a "
        "different framework rather than a variant of this one. The model "
        "reports when it cannot value a name credibly: implied growth far "
        "above delivered history, or terminal value dominating enterprise "
        "value, are flagged as diagnostics, not results."
    ),
}

STATUS_BG = {
    'RECONCILED': 'linear-gradient(135deg,#16a34a,#0f7535)',
    'FLAGGED': 'linear-gradient(135deg,#d97706,#a35603)',
    'OUT OF SCOPE': 'linear-gradient(135deg,#475569,#334155)',
}

# Choice, not a standard: how far the best- and worst-scoring checklists must
# diverge in pass-ratio (0-1) before the briefing describes the screens as "in
# conflict" rather than "broadly in agreement". Presentation wording only — it
# changes no calculation.
CONFLICT_SPREAD_THRESHOLD = 0.34

CSS = """
:root{
  --navy:#0a1628; --pos:#16a34a; --neg:#dc2626; --amber:#d97706;
  --ink:#0f172a; --muted:#64748b; --line:#e2e8f0; --bg:#eef1f6;
}
*{box-sizing:border-box;}
body{margin:0;background:var(--bg);color:var(--ink);
  font-family:"Inter","Segoe UI",-apple-system,Roboto,Helvetica,Arial,sans-serif;
  -webkit-font-smoothing:antialiased;line-height:1.45;}
.topbar{height:4px;width:100%;
  background:linear-gradient(90deg,#0a1628 0%,#2563eb 50%,#14b8a6 100%);
  position:sticky;top:0;z-index:50;}
.masthead{color:#fff;padding:30px 0 26px;border-bottom:3px solid #1e3a5f;
  background:linear-gradient(120deg,#0a1628,#112844,#0a1628,#0d2137);
  background-size:300% 300%;animation:mastShift 18s ease infinite,mastFade .9s ease both;}
@keyframes mastShift{0%{background-position:0% 50%;}50%{background-position:100% 50%;}100%{background-position:0% 50%;}}
@keyframes mastFade{from{opacity:0;}to{opacity:1;}}
.masthead .inner{max-width:980px;margin:0 auto;padding:0 24px;display:flex;
  justify-content:space-between;align-items:flex-end;flex-wrap:wrap;gap:16px;}
.masthead h1{margin:0;font-size:31px;font-weight:700;letter-spacing:-.5px;
  font-family:Georgia,"Times New Roman",serif;}
.masthead .sub{color:#93c5fd;font-size:13px;margin-top:8px;font-weight:500;}
.masthead .date{color:#94a3b8;font-size:11px;margin-top:8px;
  text-transform:uppercase;letter-spacing:1.4px;}
.masthead .right{text-align:right;}
.masthead .status-lbl{font-size:11px;color:#94a3b8;text-transform:uppercase;letter-spacing:1px;}
.masthead .status-badge{display:inline-block;margin-top:6px;padding:8px 18px;
  border-radius:999px;font-weight:700;font-size:15px;color:#fff;letter-spacing:.5px;
  box-shadow:0 2px 6px rgba(10,22,40,.3);}
.wrap{max-width:980px;margin:0 auto;padding:26px 24px 64px;}
.card{background:#fff;border:1px solid var(--line);border-radius:12px;
  padding:22px 24px;margin-bottom:22px;
  box-shadow:0 1px 2px rgba(15,23,42,.04),0 4px 12px rgba(15,23,42,.05);}
.reveal{opacity:0;transform:translateY(26px);
  transition:opacity .6s ease,transform .6s cubic-bezier(.22,.61,.36,1);}
.reveal.visible{opacity:1;transform:translateY(0);}
@media (prefers-reduced-motion:reduce){
  .reveal{opacity:1;transform:none;transition:none;}
  .masthead{animation:none;}
}
.card>h2{margin:0 0 18px;font-size:13px;font-weight:700;color:var(--muted);
  text-transform:uppercase;letter-spacing:1.5px;padding-bottom:12px;
  border-bottom:1px solid var(--line);}
.brief{background:var(--navy);border:none;color:#e2e8f0;}
.brief>h2{color:#93c5fd;border-bottom:1px solid #1e3a5f;}
.brief-lead{font-size:16px;line-height:1.7;color:#f1f5f9;margin:0;
  font-family:Georgia,"Times New Roman",serif;}
.brief .explain{color:#93a3b8;border-top:1px dashed #1e3a5f;}
.kpi-row{display:flex;flex-wrap:wrap;gap:14px;}
.kpi{flex:1 1 150px;background:#f8fafc;border:1px solid var(--line);
  border-radius:10px;padding:14px 16px;}
.kpi-label{font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.6px;}
.kpi-value{font-size:24px;font-weight:700;margin-top:6px;font-variant-numeric:tabular-nums;}
.kpi-sub{font-size:12px;margin-top:6px;font-weight:600;}
.flag{display:inline-block;padding:2px 8px;border-radius:5px;font-size:11px;font-weight:700;}
.flag-pos{background:#dcfce7;color:#166534;}
.flag-neg{background:#fee2e2;color:#991b1b;}
.flag-mut{background:#e2e8f0;color:#475569;}
table{width:100%;border-collapse:collapse;font-size:14px;}
th,td{padding:10px;text-align:right;border-bottom:1px solid var(--line);
  font-variant-numeric:tabular-nums;}
th{color:var(--muted);font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.5px;}
th.left,td.left{text-align:left;}
td.left{font-weight:600;}
tbody tr:last-child td{border-bottom:none;}
tr.implied td{background:#fff7e0;font-weight:700;color:var(--ink);}
tr.implied td.left{border-left:3px solid var(--amber);}
.alert{padding:12px 16px;border-radius:8px;margin:0 0 14px;font-size:14px;
  font-weight:500;line-height:1.5;}
.alert-ok{background:#f0fdf4;border-left:4px solid var(--pos);color:#166534;}
.alert-flag{background:#fffbeb;border-left:4px solid var(--amber);color:#92400e;}
.alert-bad{background:#fef2f2;border-left:4px solid var(--neg);color:#991b1b;}
.dcf-meta{display:flex;flex-wrap:wrap;gap:8px 22px;font-size:13px;color:var(--muted);margin:0 0 16px;}
.dcf-meta b{color:var(--ink);font-weight:600;font-variant-numeric:tabular-nums;}
.chart{margin:0;text-align:center;}
.chart img{max-width:100%;height:auto;}
.frameworks{display:grid;grid-template-columns:1fr 1fr;gap:20px 30px;}
.fw-title{font-size:13px;font-weight:700;color:var(--ink);margin:0 0 8px;
  display:flex;justify-content:space-between;padding-bottom:6px;border-bottom:1px solid var(--line);}
.fw-score{color:var(--muted);font-weight:600;font-variant-numeric:tabular-nums;}
.chk{font-size:13px;padding:4px 0;color:#334155;}
.chk .m{font-weight:700;margin-right:8px;}
.chk.pass .m{color:var(--pos);}
.chk.fail .m{color:var(--neg);}
.chk.diag{color:var(--muted);}
.explain{color:var(--muted);font-size:14px;margin:16px 0 0;padding-top:14px;
  border-top:1px dashed var(--line);line-height:1.6;}
footer{text-align:center;color:#94a3b8;font-size:12px;margin-top:8px;line-height:1.7;}
@media (max-width:640px){.frameworks{grid-template-columns:1fr;}}
"""

REVEAL_JS = """
(function(){
  "use strict";
  var reduce = window.matchMedia &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var cards = Array.prototype.slice.call(document.querySelectorAll(".reveal"));
  if (reduce || !("IntersectionObserver" in window)) {
    cards.forEach(function(c){ c.classList.add("visible"); });
  } else {
    var io = new IntersectionObserver(function(entries){
      entries.forEach(function(e){
        if (e.isIntersecting){ e.target.classList.add("visible"); io.unobserve(e.target); }
      });
    }, { threshold: 0.12, rootMargin: "0px 0px -40px 0px" });
    cards.forEach(function(c){ io.observe(c); });
  }
})();
"""

FONT_LINK = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700'
    '&display=swap" rel="stylesheet">'
)


# --- formatting helpers -----------------------------------------------------

def _na(v):
    return v is None or v != v


def _num(v, dp=2):
    return "n/a" if _na(v) else f"{v:,.{dp}f}"


def _pct(v, dp=2):
    return "n/a" if _na(v) else f"{v * 100:.{dp}f}%"


def _signed_pct(v, dp=1):
    return "n/a" if _na(v) else f"{v:+.{dp}f}%"


def _money(v):
    if _na(v):
        return "n/a"
    a = abs(v)
    if a >= 1e9:
        return f"{v / 1e9:,.1f}B"
    if a >= 1e6:
        return f"{v / 1e6:,.1f}M"
    return f"{v:,.0f}"


def _esc(s):
    return html.escape(str(s))


def _explain(key, style=""):
    """Render the static educational explain block for `key` from EXPLANATIONS."""
    st = f' style="{style}"' if style else ''
    return f'<p class="explain"{st}>{_esc(EXPLANATIONS[key])}</p>'


# --- synthesis (mechanical, no view) ----------------------------------------

_CAMP = {
    'Buffett quality': 'business quality',
    'Bajaj compounder': 'compounding durability',
    'Graham value': 'deep-value cheapness',
    'Lynch GARP': 'growth at a reasonable price',
    'Greenblatt magic': 'earnings-yield-and-ROIC rank',
    'Goldberg technical': 'technical health',
    'Inglis-Jones / Gleave': 'free-cash-flow and momentum',
}


def _conflict_sentence(a):
    cl = a['checklists']
    ratios = {n: (c['score'] / c['total'] if c['total'] else 0.0, c['score'], c['total'])
              for n, c in cl.items()}
    if not ratios:
        return ""
    best = max(ratios, key=lambda k: ratios[k][0])
    worst = min(ratios, key=lambda k: ratios[k][0])
    hr, hs, ht = ratios[best]
    lr, ls, lt = ratios[worst]
    if best == worst or hr - lr < CONFLICT_SPREAD_THRESHOLD:
        return (f"The seven screens broadly agree, with no sharp framework conflict "
                f"(scores span {ls}/{lt} to {hs}/{ht}).")
    return (f"The screens conflict: {best} is the strongest fit ({hs}/{ht}) while "
            f"{worst} is the weakest ({ls}/{lt}) — a split between "
            f"{_CAMP.get(best, best)} and {_CAMP.get(worst, worst)}.")


def _synthesis(a, r):
    reconciled = r.get('reconciled')
    flags = r.get('flags') or []
    err = r.get('error')
    g = r.get('implied_growth')
    cagr = r.get('hist_rev_cagr')
    base_fcf = r.get('base_fcf')
    tv = r.get('implied_tv_share')
    parts = []

    # Lead with unreliability whenever the model is flagged.
    if err:
        parts.append(f"The reverse DCF could not be built ({err}), so its valuation "
                     "output is unavailable and only the screens below carry information.")
    elif not reconciled:
        neg = base_fcf is not None and base_fcf < 0
        why = " because normalised free cash flow is negative" if neg else ""
        parts.append("The reverse DCF does not reconcile to the market price at any growth "
                     f"rate between 2% and 30%{why}, so its implied-growth read is "
                     "unavailable and the valuation is diagnostic rather than a number to lean on.")
    elif flags:
        parts.append("Plausibility flags fired on the reverse DCF, so its point estimate is "
                     "unreliable and should be read as a diagnostic, not a valuation.")

    if reconciled and g is not None:
        if cagr is not None:
            if g > cagr:
                gap = (f"clearing today's price requires free cash flow to compound faster "
                       f"than revenue has historically ({g:.0%} vs {cagr:.1%} CAGR).")
            else:
                gap = (f"today's price is covered by free-cash-flow growth at or below the "
                       f"historical revenue rate ({g:.0%} vs {cagr:.1%} CAGR).")
            parts.append(f"The market is pricing in roughly {g:.0%} annual free-cash-flow "
                         f"growth over five years; {gap}")
        else:
            parts.append(f"The market is pricing in roughly {g:.0%} annual free-cash-flow "
                         "growth over five years; no historical revenue CAGR is available "
                         "to compare it against.")

    conflict = _conflict_sentence(a)
    if conflict:
        parts.append(conflict)

    if reconciled and flags:
        parts.append("Specifically: " + " ".join(flags))
    elif reconciled and not flags and tv is not None:
        parts.append(f"No plausibility flags fired; terminal value is {tv:.0%} of enterprise value.")

    return " ".join(parts)


# --- chart ------------------------------------------------------------------

def _price_chart_b64(ticker):
    try:
        h = yf.Ticker(ticker).history(period="1y")
        if not len(h):
            return None
        close = h['Close']
        ma50 = close.rolling(50).mean()
        ma200 = close.rolling(200).mean()
        fig, ax = plt.subplots(figsize=(8.7, 3.1), dpi=130)
        ax.plot(close.index, close.values, color='#0a1628', lw=1.7, label='Close')
        ax.plot(ma50.index, ma50.values, color='#2563eb', lw=1.1, label='50d MA')
        ax.plot(ma200.index, ma200.values, color='#14b8a6', lw=1.1, label='200d MA')
        ax.legend(loc='best', frameon=False, fontsize=8.5)
        ax.grid(True, color='#e2e8f0', lw=.6)
        for side in ('top', 'right'):
            ax.spines[side].set_visible(False)
        for side in ('left', 'bottom'):
            ax.spines[side].set_color('#e2e8f0')
        ax.tick_params(labelsize=8, colors='#64748b')
        fig.tight_layout()
        buf = io.BytesIO()
        fig.savefig(buf, format='png', bbox_inches='tight')
        plt.close(fig)
        return base64.b64encode(buf.getvalue()).decode('ascii')
    except Exception:
        return None


# --- card builders ----------------------------------------------------------

def _status(a, r):
    if a.get('out_of_scope'):
        return 'OUT OF SCOPE'
    if r.get('error') or (r.get('flags') or []) or not r.get('reconciled'):
        return 'FLAGGED'
    return 'RECONCILED'


def _masthead(a, status):
    bg = STATUS_BG.get(status, STATUS_BG['OUT OF SCOPE'])
    name = _esc(a.get('header', {}).get('long_name') or a['ticker'])
    sector = _esc(a.get('sector') or '—')
    date_str = datetime.datetime.now().strftime("%A, %d %B %Y")
    return f"""
<div class="topbar"></div>
<div class="masthead">
  <div class="inner">
    <div>
      <h1>{name}</h1>
      <div class="sub">{_esc(a['ticker'])} &middot; {sector}</div>
      <div class="date">{_esc(date_str)}</div>
    </div>
    <div class="right">
      <div class="status-lbl">Model Status</div>
      <div class="status-badge" style="background:{bg}">{_esc(status)}</div>
    </div>
  </div>
</div>"""


def _brief_card(a, r):
    lead = _esc(_synthesis(a, r))
    return f"""
<section class="card brief reveal">
  <h2>Briefing</h2>
  <p class="brief-lead">{lead}</p>
</section>"""


def _kpi_card(a):
    h = a['header']
    price, ma, wacc, roic, mom = (h['price'], h['ma_200'], h['wacc'],
                                  h['roic'], h['momentum_12_1'])
    # ROIC vs WACC and momentum sign drive the small green/red flags.
    if _na(roic) or _na(wacc):
        roic_flag = '<span class="flag flag-mut">n/a vs WACC</span>'
    elif roic > wacc:
        roic_flag = '<span class="flag flag-pos">Above WACC</span>'
    else:
        roic_flag = '<span class="flag flag-neg">Below WACC</span>'
    if _na(mom):
        mom_flag = '<span class="flag flag-mut">n/a</span>'
    elif mom > 0:
        mom_flag = '<span class="flag flag-pos">Positive</span>'
    else:
        mom_flag = '<span class="flag flag-neg">Negative</span>'
    if _na(price) or _na(ma):
        price_flag = ''
    elif price > ma:
        price_flag = '<div class="kpi-sub"><span class="flag flag-pos">Above 200d</span></div>'
    else:
        price_flag = '<div class="kpi-sub"><span class="flag flag-neg">Below 200d</span></div>'

    return f"""
<section class="card reveal">
  <h2>Key Metrics</h2>
  <div class="kpi-row">
    <div class="kpi"><div class="kpi-label">Price</div>
      <div class="kpi-value">{_num(price)}</div>{price_flag}</div>
    <div class="kpi"><div class="kpi-label">200-day MA</div>
      <div class="kpi-value">{_num(ma)}</div></div>
    <div class="kpi"><div class="kpi-label">WACC</div>
      <div class="kpi-value">{_pct(wacc)}</div></div>
    <div class="kpi"><div class="kpi-label">ROIC</div>
      <div class="kpi-value">{_pct(roic)}</div>
      <div class="kpi-sub">{roic_flag}</div></div>
    <div class="kpi"><div class="kpi-label">12-1 Momentum</div>
      <div class="kpi-value">{_signed_pct(mom)}</div>
      <div class="kpi-sub">{mom_flag}</div></div>
  </div>
  {_explain('kpi')}
  {_explain('momentum')}
</section>"""


def _chart_card(ticker):
    b64 = _price_chart_b64(ticker)
    if b64:
        img = f'<div class="chart"><img alt="1-year price chart" src="data:image/png;base64,{b64}"></div>'
    else:
        img = '<p class="alert alert-flag">Price chart unavailable.</p>'
    return f"""
<section class="card reveal">
  <h2>Price &middot; 1 Year</h2>
  {img}
  {_explain('chart')}
</section>"""


def _reverse_dcf_card(r):
    if r.get('error'):
        body = f'<p class="alert alert-bad">{_esc(r["error"])}</p>'
    else:
        alerts = []
        if r.get('reconciled'):
            alerts.append(f'<p class="alert alert-ok"><b>Implied 5-year FCF growth: '
                          f'{r["implied_growth"]:.0%}</b> &middot; terminal value '
                          f'{_pct(r["implied_tv_share"], dp=0)} of EV</p>')
        for flag in (r.get('flags') or []):
            cls = 'alert-bad' if not r.get('reconciled') else 'alert-flag'
            alerts.append(f'<p class="alert {cls}">&#9888; {_esc(flag)}</p>')

        meta = (f'<div class="dcf-meta">'
                f'<span>Base FCF <b>{_money(r.get("base_fcf"))}</b></span>'
                f'<span>WACC <b>{_pct(r.get("wacc"))}</b></span>'
                f'<span>Terminal growth <b>{_pct(r.get("terminal_growth"), dp=1)}</b></span>'
                f'<span>Hist. revenue CAGR <b>{_pct(r.get("hist_rev_cagr"), dp=1)}</b></span>'
                f'<span>Current price <b>{_num(r.get("current_price"))}</b></span></div>')

        rows = []
        for row in r.get('rows', []):
            cls = ' class="implied"' if row['is_market'] else ''
            tv = 'n/a' if _na(row['tv_share']) else f"{row['tv_share'] * 100:.0f}%"
            rows.append(f'<tr{cls}><td class="left">{row["growth"]:.0%}</td>'
                        f'<td>{row["value"]:,.2f}</td><td>{tv}</td></tr>')
        table = (f'<table><thead><tr><th class="left">5yr FCF Growth</th>'
                 f'<th>Value / Share</th><th>TV % of EV</th></tr></thead>'
                 f'<tbody>{"".join(rows)}</tbody></table>')
        body = "".join(alerts) + meta + table

    return f"""
<section class="card reveal">
  <h2>Reverse DCF &middot; Growth Implied by Price</h2>
  {body}
  {_explain('reverse_dcf')}
  {_explain('base_fcf')}
  {_explain('terminal_value')}
</section>"""


def _relative_card(a):
    rows = []
    for rv in a.get('relative_valuation', []):
        pctile = 'n/a' if _na(rv['percentile']) else f"{rv['percentile']:.0f}"
        rows.append(f'<tr><td class="left">{_esc(rv["label"])}</td>'
                    f'<td>{_num(rv["target"])}</td><td>{_num(rv["median"])}</td>'
                    f'<td>{pctile}</td><td>{rv["n"]}</td></tr>')
    table = (f'<table><thead><tr><th class="left">Multiple</th><th>Target</th>'
             f'<th>Sector Median</th><th>Percentile</th><th>Peers</th></tr></thead>'
             f'<tbody>{"".join(rows)}</tbody></table>')
    return f"""
<section class="card reveal">
  <h2>Relative Valuation &middot; vs Sector</h2>
  <p style="font-size:13px;color:var(--muted);margin:0 0 14px;">
    Percentile is the raw position of the multiple among peers — lower means cheaper than the sector.</p>
  {table}
  {_explain('relative_valuation')}
</section>"""


def _checklists_card(a):
    blocks = []
    for name, c in a['checklists'].items():
        lines = []
        for rule, passed in c['rules'].items():
            cls = 'pass' if passed else 'fail'
            mark = '&#10003;' if passed else '&#10007;'
            lines.append(f'<div class="chk {cls}"><span class="m">{mark}</span>{_esc(rule)}</div>')
        for rule, val in c['diagnostics'].items():
            shown = round(val, 1) if isinstance(val, (int, float)) else val
            lines.append(f'<div class="chk diag"><span class="m">&#8211;</span>'
                         f'{_esc(rule)} = {_esc(shown)}</div>')
        blocks.append(f'<div class="fw"><div class="fw-title"><span>{_esc(name)}</span>'
                      f'<span class="fw-score">{c["score"]}/{c["total"]}</span></div>'
                      f'{"".join(lines)}</div>')
    return f"""
<section class="card reveal">
  <h2>Screening Checklists</h2>
  <div class="frameworks">{"".join(blocks)}</div>
  {_explain('checklists')}
</section>"""


def _scope_card(a):
    msg = _esc(a['scope_message']).replace('\n', '<br>')
    return f"""
<section class="card brief reveal">
  <h2>Out of Scope</h2>
  <p class="brief-lead">{msg}</p>
</section>"""


def _footer():
    # Built at render time, not import time, so the generation timestamp is
    # current on a warm (long-running) Streamlit server.
    stamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
    return f"""
<footer>
  {_explain('methodology', 'text-align:left;color:var(--muted);')}
  <div style="margin-top:16px;">Generated {stamp}
  &middot; market data via Yahoo Finance &middot; for informational purposes only — not
  investment advice.</div>
</footer>"""


def _document(body):
    return (f'<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<title>Equity Report</title>{FONT_LINK}<style>{CSS}</style></head>'
            f'<body>{body}<script>{REVEAL_JS}</script></body></html>')


def build_report_html(ticker):
    """Return a complete, self-contained HTML report for `ticker`."""
    a = analyse(ticker)
    if a.get('out_of_scope'):
        body = (_masthead(a, 'OUT OF SCOPE')
                + f'<div class="wrap">{_scope_card(a)}{_footer()}</div>')
        return _document(body)

    r = reverse_dcf(ticker)
    status = _status(a, r)
    body = (_masthead(a, status) + '<div class="wrap">'
            + _brief_card(a, r)
            + _kpi_card(a)
            + _chart_card(a['ticker'])
            + _reverse_dcf_card(r)
            + _relative_card(a)
            + _checklists_card(a)
            + _footer() + '</div>')
    return _document(body)


if __name__ == "__main__":
    import sys
    tk = sys.argv[1] if len(sys.argv) > 1 else "MSFT"
    # Write raw UTF-8 bytes so `python report.py MSFT > out.html` stays UTF-8 on
    # Windows (stdout defaults to cp1252 there, which would corrupt em-dashes).
    sys.stdout.buffer.write(build_report_html(tk).encode("utf-8"))
