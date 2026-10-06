"""QUASAR dashboard — trading-terminal redesign.

Clean, single-page view of the bot's health:
  · Hero: portfolio equity curve (the centerpiece)
  · KPI strip: CAGR · Sharpe · Max DD · Paper P&L
  · Positions: live signals with directional pills + size bars
  · Book: cash / exposure / equity, plus recent fills

Run:  streamlit run dashboard/app.py
"""
from __future__ import annotations
import os
import sys
import json
import subprocess
import datetime as dt
import pandas as pd
import numpy as np
import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from quasar.config import load_config

ROOT = os.path.dirname(__file__)
UP, DOWN, ACCENT = "#2ebd85", "#f6465d", "#4f8cff"

st.set_page_config(page_title="QUASAR", page_icon="◆", layout="wide",
                  theme={"base": "dark", "primaryColor": ACCENT,
                         "backgroundColor": "#0a0e14", "secondaryBackgroundColor": "#131722",
                         "textColor": "#e6e9ef"})

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@500;700&display=swap');
#MainMenu, header[data-testid="stHeader"], footer, #stDecoration {visibility:hidden !important;}
.stApp {background:#0a0e14;}
.block-container {max-width:1180px; margin:0 auto; padding:22px 26px 40px;}
* {font-family:'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;}
.mono {font-family:'JetBrains Mono',ui-monospace,SFMono-Regular,Menlo,monospace;}
.topbar {display:flex; align-items:center; justify-content:space-between;
         padding:6px 4px 18px; border-bottom:1px solid #232a39; margin-bottom:22px;}
.brand {font-size:22px; font-weight:800; letter-spacing:3px; color:#e6e9ef;}
.brand b {color:ACCENT;}
.brand small {display:block; font-size:11px; letter-spacing:1.5px; font-weight:500;
              color:#7a8294; margin-top:2px; text-transform:uppercase;}
.tag {font-size:11px; font-weight:700; letter-spacing:.6px; padding:4px 11px; border-radius:999px;}
.tag-paper {background:rgba(79,140,255,.14); color:ACCENT; border:1px solid rgba(79,140,255,.4);}
.tag-live {background:rgba(246,70,93,.15); color:#f6465d; border:1px solid rgba(246,70,93,.4);}
.upd {font-size:11px; color:#7a8294; margin-top:6px;}
.card {background:#131722; border:1px solid #232a39; border-radius:14px; padding:16px 18px; margin-bottom:16px;}
.card-h {display:flex; align-items:baseline; justify-content:space-between; margin-bottom:10px;}
.card-h .t {font-size:13px; font-weight:600; letter-spacing:.4px; color:#e6e9ef;}
.card-h .s {font-size:11px; color:#7a8294;}
.kpis {display:grid; grid-template-columns:repeat(4,1fr); gap:14px; margin-bottom:16px;}
.kpi {background:#131722; border:1px solid #232a39; border-radius:14px; padding:15px 17px;}
.kpi .l {font-size:10.5px; letter-spacing:.7px; text-transform:uppercase; color:#7a8294;}
.kpi .v {font-size:25px; font-weight:700; margin-top:7px; line-height:1;}
.kpi .x {font-size:11.5px; margin-top:6px; color:#7a8294;}
table.t {width:100%; border-collapse:collapse; font-size:13px;}
table.t th {text-align:left; color:#7a8294; font-weight:600; font-size:10.5px;
            text-transform:uppercase; letter-spacing:.5px; padding:8px 10px; border-bottom:1px solid #232a39;}
table.t td {padding:9px 10px; border-bottom:1px solid rgba(35,42,57,.6); color:#e6e9ef;}
.pill {display:inline-block; padding:2px 9px; border-radius:999px; font-size:11.5px; font-weight:700;}
.pill-l {background:rgba(46,189,133,.15); color:#2ebd85; border:1px solid rgba(46,189,133,.4);}
.pill-s {background:rgba(246,70,93,.15); color:#f6465d; border:1px solid rgba(246,70,93,.4);}
.bar {height:6px; border-radius:4px; background:#1b2130; overflow:hidden; min-width:70px;}
.bar > i {display:block; height:100%;}
.empty {color:#7a8294; font-size:13px; padding:14px 4px;}
.foot {color:#5b6472; font-size:11.5px; text-align:center; margin-top:26px; letter-spacing:.5px;}
.sb {color:#e6e9ef; font-size:13px;}
</style>
"""
st.markdown(CSS.replace("ACCENT", ACCENT), unsafe_allow_html=True)


# ---- loaders -----------------------------------------------------------------
def load_backtest():
    p = os.path.join(ROOT, "data", "equity_curve.csv")
    if not os.path.exists(p):
        return None
    eq = pd.read_csv(p, index_col=0, parse_dates=True).iloc[:, 0]
    n = max((eq.index[-1] - eq.index[0]).days / 365.25, 1e-9)
    cagr = (eq.iloc[-1] / eq.iloc[0]) ** (1 / n) - 1
    d = eq.pct_change().dropna()
    sharpe = d.mean() / (d.std() + 1e-12) * np.sqrt(252)
    return eq, dict(cagr=cagr, sharpe=sharpe, dd=(eq / eq.cummax() - 1).min(), final=float(eq.iloc[-1]))


def load_state():
    p = os.path.join(ROOT, "data", "state.json")
    return json.load(open(p)) if os.path.exists(p) else None


def load_trades():
    p = os.path.join(ROOT, "data", "trades.csv")
    return pd.read_csv(p) if os.path.exists(p) else None


def run_step():
    subprocess.run([sys.executable, "-m", "quasar.paper.trader", "--once"], cwd=ROOT,
                   env={**os.environ, "PYTHONPATH": os.path.join(ROOT, "src")},
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


# ---- data --------------------------------------------------------------------
cfg = load_config()
active = cfg.get("strategy.active")
live = bool(cfg.get("broker.live_trading", False))
bt = load_backtest()
state = load_state()
initial = cfg.get("backtest.initial_capital", 1_000_000.0)
peq = state["equity_curve"][-1]["equity"] if (state and state.get("equity_curve")) else None
pnl = (peq - initial) if peq else None
now = dt.datetime.now().strftime("%d %b %Y, %H:%M")


# ---- top bar -----------------------------------------------------------------
mode_tag = '<span class="tag tag-live">LIVE</span>' if live else '<span class="tag tag-paper">PAPER</span>'
st.markdown(
    f'<div class="topbar"><div class="brand"><b>QUASAR</b>'
    f'<small>Systematic F&amp;O Trading Bot</small></div>'
    f'<div style="text-align:right">{mode_tag}'
    f'<div class="upd">strategy: {active} · updated {now}</div></div></div>',
    unsafe_allow_html=True)


# ---- hero: equity curve ------------------------------------------------------
hero_sub = f"₹{bt[1]['final']:,.0f} · CAGR {bt[1]['cagr']*100:.1f}%" if bt else "no backtest yet"
st.markdown(f'<div class="card"><div class="card-h"><span class="t">Portfolio Equity</span>'
            f'<span class="s">{hero_sub}</span></div>', unsafe_allow_html=True)
if bt:
    st.area_chart(bt[0], height=300, use_container_width=True, color=ACCENT)
else:
    st.info("Run `python scripts/backtest.py --save` to populate.")
st.markdown('</div>', unsafe_allow_html=True)


# ---- KPI strip ---------------------------------------------------------------
def kpi(label, value, sub, color="#e6e9ef"):
    return (f'<div class="kpi"><div class="l">{label}</div>'
            f'<div class="v mono" style="color:{color}">{value}</div>'
            f'<div class="x">{sub}</div></div>')

cagr = f"{bt[1]['cagr']*100:.1f}%" if bt else "—"
sh = f"{bt[1]['sharpe']:.2f}" if bt else "—"
dd = f"{bt[1]['dd']*100:.1f}%" if bt else "—"
pnl_s = f"{pnl:+,.0f}" if pnl is not None else "—"
pnl_c = UP if (pnl or 0) >= 0 else DOWN
pnl_x = f"{(pnl/initial*100):+.1f}% vs start" if pnl is not None else "no paper state"
st.markdown(
    f'<div class="kpis">{kpi("Backtest CAGR", cagr, "vol-targeted trend", ACCENT)}'
    f'{kpi("Sharpe", sh, "risk-adjusted", "#e6e9ef")}'
    f'{kpi("Max Drawdown", dd, "peak-to-trough", DOWN)}'
    f'{kpi("Paper P&L", pnl_s, pnl_x, pnl_c)}</div>', unsafe_allow_html=True)


# ---- lower section: positions + book -----------------------------------------
sig = state.get("last_signal") if state else None
rows = ""
if sig:
    for k, v in sig.items():
        if v == 0:
            continue
        lng = v > 0
        pill = f'<span class="pill {"pill-l" if lng else "pill-s"}">{"LONG" if lng else "SHORT"}</span>'
        bar = f'<div class="bar"><i style="width:min({abs(v)*100:.0f},100)%;background:{"#2ebd85" if lng else "#f6465d"}"></i></div>'
        rows += f'<tr><td class="mono">{k}</td><td>{pill}</td><td class="mono">{v:+.3f}</td><td>{bar}</td></tr>'
left = '<div class="card"><div class="card-h"><span class="t">Open Signals</span>' \
       '<span class="s">signed leverage</span></div>'
left += (f'<table class="t"><tr><th>Instrument</th><th>Dir</th><th>Weight</th><th>Size</th></tr>{rows}</table>'
         if rows else '<div class="empty">No open positions — bot is flat (between signals).</div>') + '</div>'

cash = state.get("cash", 0) if state else 0
shares = state.get("shares", {}) if state else {}
expo = 0.0
try:
    from quasar.data.feed import build_feed
    px = build_feed().latest(list(shares.keys()))
    expo = sum(int(q) * px.get(k, 0.0) for k, q in shares.items())
except Exception:
    pass
right = '<div class="card"><div class="card-h"><span class="t">Paper Book</span>' \
        '<span class="s">simulated</span></div>' \
        f'<table class="t"><tr><th>Metric</th><th style="text-align:right">Value</th></tr>' \
        f'<tr><td>Equity</td><td class="mono" style="text-align:right">₹{(peq or 0):,.0f}</td></tr>' \
        f'<tr><td>Cash</td><td class="mono" style="text-align:right">₹{cash:,.0f}</td></tr>' \
        f'<tr><td>Exposure</td><td class="mono" style="text-align:right">₹{expo:,.0f}</td></tr>' \
        f'<tr><td>Positions</td><td class="mono" style="text-align:right">{len(shares)}</td></tr>' \
        '</table></div>'

lc, rc = st.columns([1.55, 1], gap="large")
with lc:
    st.markdown(left, unsafe_allow_html=True)
with rc:
    st.markdown(right, unsafe_allow_html=True)
    if state and state.get("equity_curve"):
        peqc = pd.Series({x["date"]: x["equity"] for x in state["equity_curve"]})
        st.line_chart(peqc, height=130, use_container_width=True, color=ACCENT)

tr = load_trades()
if tr is not None and not tr.empty:
    trows = ""
    for _, r in tr.tail(8).iterrows():
        side = str(r.get("side", "")).upper()
        sc = "#2ebd85" if side == "BUY" else "#f6465d"
        trows += (f'<tr><td class="mono">{r.get("symbol","")}</td>'
                  f'<td class="mono" style="color:{sc}">{side}</td>'
                  f'<td class="mono" style="text-align:right">{r.get("qty",0):,}</td>'
                  f'<td class="mono" style="text-align:right">{r.get("price",0):.2f}</td></tr>')
    st.markdown(f'<div class="card"><div class="card-h"><span class="t">Recent Fills</span></div>'
                f'<table class="t"><tr><th>Symbol</th><th>Side</th>'
                f'<th style="text-align:right">Qty</th><th style="text-align:right">Price</th></tr>'
                f'{trows}</table></div>', unsafe_allow_html=True)


# ---- sidebar (actions only) --------------------------------------------------
st.sidebar.markdown(f'<div class="sb" style="font-weight:700;font-size:15px;'
                    f'letter-spacing:1px;color:{ACCENT}">QUASAR</div>', unsafe_allow_html=True)
st.sidebar.caption(f"mode: {'LIVE' if live else 'PAPER'} · {active}")
if st.sidebar.button("↻ Refresh signals", use_container_width=True):
    with st.spinner("Fetching market data…"):
        run_step()
    st.rerun()
if st.sidebar.button("⟳ Re-run backtest", use_container_width=True):
    with st.spinner("Backtesting (a few minutes)…"):
        subprocess.run([sys.executable, "scripts/backtest.py", "--save"], cwd=ROOT,
                       env={**os.environ, "PYTHONPATH": os.path.join(ROOT, "src")},
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    st.rerun()

st.markdown('<div class="foot">QUASAR · powered by Hy3</div>', unsafe_allow_html=True)
