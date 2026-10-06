"""QUASAR dashboard — hand-built trading terminal.

Every chart is rendered as custom SVG (no default Streamlit charts) for a
cohesive, premium look:
  · Hero: strategy equity curve (gradient area) + dominant value
  · KPI tiles: CAGR · Sharpe · Max DD · Volatility · Paper P&L (each w/ spark)
  · Allocation donut (long / short / cash) + Open Signals table
  · Drawdown curve + Yearly Returns bars (factsheet style) + Recent Fills

Run:  streamlit run dashboard/app.py
"""
from __future__ import annotations
import os
import sys
import json
import math
import subprocess
import datetime as dt
import pandas as pd
import numpy as np
import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from quasar.config import load_config

ROOT = os.path.dirname(os.path.dirname(__file__))  # repo root (data/ lives here)
UP, DOWN, ACCENT = "#2ebd85", "#f6465d", "#4f8cff"


# ---------------------------------------------------------------------------
# SVG chart builders (full visual control, no external deps)
# ---------------------------------------------------------------------------
def _scale(series, w, h, pad=14):
    s = series.dropna()
    xs = np.linspace(0, w, len(s))
    lo, hi = s.min(), s.max()
    rng = (hi - lo) or 1.0
    ys = h - pad - (s - lo) / rng * (h - 2 * pad)
    return xs, ys, lo, hi


def svg_area(series, w=860, h=260, color=ACCENT, gid="g", with_axes=True):
    if len(series.dropna()) < 2:
        return ""
    xs, ys, lo, hi = _scale(series, w, h)
    pts = list(zip(xs, ys))
    d_line = "M" + " L".join(f"{x:.1f} {y:.1f}" for x, y in pts)
    d_area = d_line + f" L{w} {h} L0 {h} Z"
    grid = ""
    if with_axes:
        for i in range(4):
            y = 14 + i * (h - 28) / 3
            grid += f'<line x1="0" y1="{y:.1f}" x2="{w}" y2="{y:.1f}" stroke="#1b2230" stroke-width="1"/>'
        grid += (f'<text x="6" y="20" fill="#5b6472" font-size="10" font-family="JetBrains Mono,monospace">'
                 f'{hi:,.0f}</text>'
                 f'<text x="6" y="{h-6}" fill="#5b6472" font-size="10" font-family="JetBrains Mono,monospace">'
                 f'{lo:,.0f}</text>')
    grad = (f'<linearGradient id="{gid}" x1="0" y1="0" x2="0" y2="1">'
            f'<stop offset="0%" stop-color="{color}" stop-opacity="0.38"/>'
            f'<stop offset="100%" stop-color="{color}" stop-opacity="0"/></linearGradient>')
    return (f'<svg viewBox="0 0 {w} {h}" width="100%" style="display:block">'
            f'<defs>{grad}</defs>{grid}'
            f'<path d="{d_area}" fill="url(#{gid})"/>'
            f'<path d="{d_line}" fill="none" stroke="{color}" stroke-width="2" '
            f'stroke-linejoin="round" stroke-linecap="round"/></svg>')


def svg_spark(series, w=130, h=36, color=ACCENT, gid="s"):
    if len(series.dropna()) < 2:
        return ""
    xs, ys, _, _ = _scale(series, w, h, pad=4)
    d = "M" + " L".join(f"{x:.1f} {y:.1f}" for x, y in zip(xs, ys))
    grad = (f'<linearGradient id="{gid}" x1="0" y1="0" x2="0" y2="1">'
            f'<stop offset="0%" stop-color="{color}" stop-opacity="0.4"/>'
            f'<stop offset="100%" stop-color="{color}" stop-opacity="0"/></linearGradient>')
    return (f'<svg viewBox="0 0 {w} {h}" width="100%" style="display:block">'
            f'<defs>{grad}</defs>'
            f'<path d="{d} L{w} {h} L0 {h} Z" fill="url(#{gid})"/>'
            f'<path d="{d}" fill="none" stroke="{color}" stroke-width="1.6" '
            f'stroke-linejoin="round" stroke-linecap="round"/></svg>')


def svg_drawdown(series, w=860, h=170, gid="dd"):
    if len(series.dropna()) < 2:
        return ""
    dd = series / series.cummax() - 1.0
    xs = np.linspace(0, w, len(dd))
    lo, hi = dd.min(), 0.0
    rng = (hi - lo) or 1.0
    pad = 14
    ys = h - pad - (dd - lo) / rng * (h - 2 * pad)
    pts = list(zip(xs, ys))
    d = "M" + " L".join(f"{x:.1f} {y:.1f}" for x, y in pts) + f" L{w} {h} L0 {h} Z"
    grad = (f'<linearGradient id="{gid}" x1="0" y1="0" x2="0" y2="1">'
            f'<stop offset="0%" stop-color="{DOWN}" stop-opacity="0"/>'
            f'<stop offset="100%" stop-color="{DOWN}" stop-opacity="0.35"/></linearGradient>')
    grid = f'<text x="6" y="18" fill="#5b6472" font-size="10" font-family="JetBrains Mono,monospace">{lo*100:.0f}%</text>'
    return (f'<svg viewBox="0 0 {w} {h}" width="100%" style="display:block">'
            f'<defs>{grad}</defs>{grid}<path d="{d}" fill="url(#{gid})"/>'
            f'<path d="M{" L".join(f"{x:.1f} {y:.1f}" for x,y in pts)}" fill="none" '
            f'stroke="{DOWN}" stroke-width="1.6"/></svg>')


def svg_bars(pairs, w=860, h=170, gid="yr"):
    if not pairs:
        return ""
    n = len(pairs)
    gap = w / n
    bw = gap * 0.56
    base = h - 24
    mx = max((abs(v) for _, v in pairs)) or 1.0
    out = f'<line x1="0" y1="{base}" x2="{w}" y2="{base}" stroke="#232a39" stroke-width="1"/>'
    for i, (lab, v) in enumerate(pairs):
        x = i * gap + (gap - bw) / 2
        bh = abs(v) / mx * (base - 12)
        col = UP if v >= 0 else DOWN
        y = base - bh if v >= 0 else base
        out += f'<rect x="{x:.1f}" y="{y:.1f}" width="{bw:.1f}" height="{bh:.1f}" rx="3" fill="{col}"/>'
        out += (f'<text x="{x+bw/2:.1f}" y="{h-8}" text-anchor="middle" fill="#7a8294" '
                f'font-size="10" font-family="Inter,sans-serif">{lab}</text>')
        out += (f'<text x="{x+bw/2:.1f}" y="{y-4 if v>=0 else y+bh+10:.1f}" text-anchor="middle" '
                f'fill="{col}" font-size="9" font-family="JetBrains Mono,monospace">'
                f'{"+" if v>=0 else ""}{v:.0f}%</text>')
    return f'<svg viewBox="0 0 {w} {h}" width="100%" style="display:block">{out}</svg>'


def svg_donut(segments, w=190, h=190, thickness=24, center=None, clabel=None):
    cx = cy = w / 2
    r = (w - thickness) / 2
    rin = r - thickness
    total = sum(max(v, 0) for _, v, _ in segments) or 1.0
    ang = 90.0
    paths = ""
    for _, val, color in segments:
        frac = max(val, 0) / total
        if frac <= 0:
            continue
        a0, a1 = ang, ang + frac * 360
        ang = a1
        large = 1 if (a1 - a0) > 180 else 0
        x0 = cx + r * math.cos(math.radians(a0)); y0 = cy - r * math.sin(math.radians(a0))
        x1 = cx + r * math.cos(math.radians(a1)); y1 = cy - r * math.sin(math.radians(a1))
        xi0 = cx + rin * math.cos(math.radians(a0)); yi0 = cy - rin * math.sin(math.radians(a0))
        xi1 = cx + rin * math.cos(math.radians(a1)); yi1 = cy - rin * math.sin(math.radians(a1))
        d = (f"M{x0:.1f} {y0:.1f} A{r} {r} 0 {large} 1 {x1:.1f} {y1:.1f} "
             f"L{xi1:.1f} {yi1:.1f} A{rin} {rin} 0 {large} 0 {xi0:.1f} {yi0:.1f} Z")
        paths += f'<path d="{d}" fill="{color}"/>'
    center_txt = (f'<text x="{cx}" y="{cy-2}" text-anchor="middle" fill="#e6e9ef" font-size="22" '
                 f'font-weight="700" font-family="JetBrains Mono,monospace">{center}</text>'
                 f'<text x="{cx}" y="{cy+15}" text-anchor="middle" fill="#7a8294" font-size="9" '
                 f'letter-spacing="1">{(clabel or "").upper()}</text>') if center else ""
    return (f'<svg viewBox="0 0 {w} {h}" width="100%" style="display:block">'
            f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="#1b2230" stroke-width="{thickness}"/>'
            f'{paths}{center_txt}</svg>')


# ---------------------------------------------------------------------------
# theme + base styles
# ---------------------------------------------------------------------------
st.set_page_config(page_title="QUASAR", page_icon="◆", layout="wide")

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@500;700&display=swap');
#MainMenu, header[data-testid="stHeader"], footer, #stDecoration {visibility:hidden !important;}
.stApp, [data-testid="stAppViewContainer"], [data-testid="stAppViewContainer"] > .main,
.stAppViewBlockContainer {background:#0a0e14 !important;}
html, body, .stApp, .stMarkdown, p, span, div {color:#e6e9ef;}
.block-container {max-width:1200px; margin:0 auto; padding:20px 28px 40px;}
* {font-family:'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;}
.mono {font-family:'JetBrains Mono',ui-monospace,SFMono-Regular,Menlo,monospace;}
.topbar {display:flex; align-items:center; justify-content:space-between; padding:4px 2px 16px;
         border-bottom:1px solid #1b2230; margin-bottom:20px;}
.brand {font-size:21px; font-weight:800; letter-spacing:3px; color:#e6e9ef;}
.brand b {color:ACCENT;}
.brand small {display:block; font-size:10.5px; letter-spacing:1.4px; font-weight:500;
              color:#7a8294; margin-top:2px; text-transform:uppercase;}
.dot {width:7px; height:7px; border-radius:50%; background:#2ebd85; display:inline-block;
       margin-right:6px; box-shadow:0 0 8px #2ebd85;}
.tag {font-size:11px; font-weight:700; letter-spacing:.6px; padding:4px 11px; border-radius:999px;}
.tag-paper {background:rgba(79,140,255,.14); color:ACCENT; border:1px solid rgba(79,140,255,.4);}
.tag-live {background:rgba(246,70,93,.15); color:#f6465d; border:1px solid rgba(246,70,93,.4);}
.upd {font-size:11px; color:#7a8294; margin-top:6px;}
.card {background:#131722; border:1px solid #1b2230; border-radius:16px; padding:18px 20px; margin-bottom:16px;}
.card-h {display:flex; align-items:baseline; justify-content:space-between; margin-bottom:12px;}
.card-h .t {font-size:12px; font-weight:600; letter-spacing:.6px; color:#9aa3b2; text-transform:uppercase;}
.card-h .s {font-size:11px; color:#5b6472;}
.hero-val {font-size:34px; font-weight:800; letter-spacing:-0.5px; line-height:1;}
.hero-sub {font-size:12px; color:#7a8294; margin-top:8px;}
.kpis {display:grid; grid-template-columns:repeat(5,1fr); gap:13px; margin-bottom:16px;}
.kpi {background:#131722; border:1px solid #1b2230; border-radius:14px; padding:14px 15px;}
.kpi .l {font-size:10px; letter-spacing:.6px; text-transform:uppercase; color:#7a8294;}
.kpi .v {font-size:21px; font-weight:700; margin-top:6px; line-height:1;}
.kpi .x {font-size:11px; margin-top:4px; color:#5b6472;}
.kpi .sp {margin-top:6px;}
.grid2 {display:grid; grid-template-columns:1fr 1fr; gap:16px; align-items:start;}
.donut-wrap {display:flex; align-items:center; gap:18px;}
table.t {width:100%; border-collapse:collapse; font-size:13px;}
table.t th {text-align:left; color:#7a8294; font-weight:600; font-size:10px; text-transform:uppercase;
            letter-spacing:.5px; padding:8px 9px; border-bottom:1px solid #1b2230;}
table.t td {padding:9px 9px; border-bottom:1px solid rgba(27,34,48,.7); color:#e6e9ef;}
.pill {display:inline-block; padding:2px 9px; border-radius:999px; font-size:11px; font-weight:700;}
.pill-l {background:rgba(46,189,133,.15); color:#2ebd85; border:1px solid rgba(46,189,133,.4);}
.pill-s {background:rgba(246,70,93,.15); color:#f6465d; border:1px solid rgba(246,70,93,.4);}
.bar {height:6px; border-radius:4px; background:#1b2230; overflow:hidden; min-width:64px;}
.bar > i {display:block; height:100%;}
.legend {display:flex; gap:14px; font-size:11px; color:#9aa3b2; margin-top:4px;}
.legend i {width:9px; height:9px; border-radius:2px; display:inline-block; margin-right:5px; vertical-align:middle;}
.empty {color:#7a8294; font-size:13px; padding:12px 4px;}
.foot {color:#5b6472; font-size:11px; text-align:center; margin-top:24px; letter-spacing:.5px;}
.sb {color:#e6e9ef; font-size:13px;}
</style>
"""
st.markdown(CSS.replace("ACCENT", ACCENT), unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# loaders
# ---------------------------------------------------------------------------
def load_backtest():
    p = os.path.join(ROOT, "data", "equity_curve.csv")
    if not os.path.exists(p):
        return None
    eq = pd.read_csv(p, index_col=0, parse_dates=True).iloc[:, 0]
    n = max((eq.index[-1] - eq.index[0]).days / 365.25, 1e-9)
    cagr = (eq.iloc[-1] / eq.iloc[0]) ** (1 / n) - 1
    d = eq.pct_change().dropna()
    sharpe = d.mean() / (d.std() + 1e-12) * np.sqrt(252)
    vol = d.std() * np.sqrt(252)
    return eq, dict(cagr=cagr, sharpe=sharpe, dd=(eq / eq.cummax() - 1).min(),
                   vol=vol, final=float(eq.iloc[-1]), ret=eq.iloc[-1] / eq.iloc[0] - 1)


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


# ---------------------------------------------------------------------------
# data
# ---------------------------------------------------------------------------
cfg = load_config()
active = cfg.get("strategy.active")
live = bool(cfg.get("broker.live_trading", False))
bt = load_backtest()
state = load_state()
initial = cfg.get("backtest.initial_capital", 1_000_000.0)
peq = state["equity_curve"][-1]["equity"] if (state and state.get("equity_curve")) else None
pnl = (peq - initial) if peq else None
now = dt.datetime.now().strftime("%d %b %Y, %H:%M")

# yearly returns from backtest
yearly = []
if bt:
    eq = bt[0]
    yend = eq.groupby(eq.index.year).last()
    for i in range(1, len(yend)):
        r = yend.iloc[i] / yend.iloc[i - 1] - 1
        yearly.append((str(yend.index[i]), r * 100))
    if len(yend) >= 1:
        pass

sig = state.get("last_signal") if state else None
long_w = sum(v for v in (sig or {}).values() if v > 0)
short_w = sum(-v for v in (sig or {}).values() if v < 0)
gross = long_w + short_w
cash_w = max(1 - gross, 0)


# ---------------------------------------------------------------------------
# top bar
# ---------------------------------------------------------------------------
mode_tag = '<span class="tag tag-live">LIVE</span>' if live else '<span class="tag tag-paper">PAPER</span>'
st.markdown(
    f'<div class="topbar"><div class="brand"><b>QUASAR</b>'
    f'<small>Systematic F&amp;O Trading Bot</small></div>'
    f'<div style="text-align:right"><span class="dot"></span>{mode_tag}'
    f'<div class="upd">strategy: {active} · updated {now}</div></div></div>',
    unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# hero — strategy equity curve
# ---------------------------------------------------------------------------
hero_val = f"₹{bt[1]['final']:,.0f}" if bt else "—"
hero_chg = (f"▲ {bt[1]['ret']*100:.0f}% total · CAGR {bt[1]['cagr']*100:.1f}%"
            if bt else "no backtest")
hero_right = (f"2016 → 2024 · ₹{initial:,.0f} → ₹{bt[1]['final']:,.0f}" if bt else "no backtest data")
st.markdown(f'<div class="card"><div class="card-h"><div>'
            f'<div class="t">Strategy Equity · Backtest</div>'
            f'<div class="hero-val mono">{hero_val}</div>'
            f'<div class="hero-sub">{hero_chg}</div></div>'
            f'<div class="s">{hero_right}</div></div>',
            unsafe_allow_html=True)
if bt:
    st.markdown(svg_area(bt[0], gid="hero"), unsafe_allow_html=True)
else:
    st.info("Run `python scripts/backtest.py --save` to populate the equity curve.")
st.markdown('</div>', unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# KPI tiles
# ---------------------------------------------------------------------------
def kpi(label, value, sub, color="#e6e9ef", spark=None, sgid="k"):
    sp = f'<div class="sp">{spark}</div>' if spark else ""
    return (f'<div class="kpi"><div class="l">{label}</div>'
            f'<div class="v mono" style="color:{color}">{value}</div>'
            f'<div class="x">{sub}</div>{sp}</div>')

cagr = f"{bt[1]['cagr']*100:.1f}%" if bt else "—"
sh = f"{bt[1]['sharpe']:.2f}" if bt else "—"
dd = f"{bt[1]['dd']*100:.1f}%" if bt else "—"
vol = f"{bt[1]['vol']*100:.1f}%" if bt else "—"
pnl_s = f"{pnl:+,.0f}" if pnl is not None else "—"
pnl_c = UP if (pnl or 0) >= 0 else DOWN
pnl_x = f"{(pnl/initial*100):+.1f}% vs start" if pnl is not None else "no paper state"
eq_spark = svg_spark(bt[0], gid="sp0") if bt else None
pq_spark = (svg_spark(pd.Series({x["date"]: x["equity"] for x in state["equity_curve"]}),
                       color=(UP if (pnl or 0) >= 0 else DOWN), gid="sp1")
            if state and state.get("equity_curve") else None)
st.markdown(
    f'<div class="kpis">'
    f'{kpi("Backtest CAGR", cagr, "vol-targeted trend", ACCENT, eq_spark, "k0")}'
    f'{kpi("Sharpe", sh, "risk-adjusted", "#e6e9ef", eq_spark, "k1")}'
    f'{kpi("Max Drawdown", dd, "peak-to-trough", DOWN, eq_spark, "k2")}'
    f'{kpi("Volatility", vol, "annualised", "#e6e9ef", eq_spark, "k3")}'
    f'{kpi("Paper P&L", pnl_s, pnl_x, pnl_c, pq_spark, "k4")}'
    f'</div>', unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# lower grid: allocation + signals  |  drawdown + yearly + fills
# ---------------------------------------------------------------------------
st.markdown('<div class="grid2">', unsafe_allow_html=True)

# --- left: allocation donut + signals ---
donut = svg_donut([("Long", long_w, UP), ("Short", short_w, DOWN), ("Cash", cash_w, "#2b3139")],
                  center=f"{gross*100:.0f}%", clabel="gross")
left = '<div class="card"><div class="card-h"><span class="t">Live Allocation</span>' \
       '<span class="s">paper book</span></div>'
left += f'<div class="donut-wrap"><div style="width:170px">{donut}</div><div class="legend">' \
       f'<div><i style="background:{UP}"></i>Long {long_w*100:.0f}%</div>' \
       f'<div><i style="background:{DOWN}"></i>Short {short_w*100:.0f}%</div>' \
       f'<div><i style="background:#2b3139"></i>Cash {cash_w*100:.0f}%</div></div></div></div>'

rows = ""
if sig:
    for k, v in sig.items():
        if v == 0:
            continue
        lng = v > 0
        pill = f'<span class="pill {"pill-l" if lng else "pill-s"}">{"LONG" if lng else "SHORT"}</span>'
        bar = f'<div class="bar"><i style="width:min({abs(v)*100:.0f},100)%;background:{"#2ebd85" if lng else "#f6465d"}"></i></div>'
        rows += f'<tr><td class="mono">{k}</td><td>{pill}</td><td class="mono">{v:+.3f}</td><td>{bar}</td></tr>'
left += '<div class="card-h" style="margin-top:14px"><span class="t">Open Signals</span>' \
        '<span class="s">signed leverage</span></div>'
left += (f'<table class="t"><tr><th>Inst</th><th>Dir</th><th>W</th><th>Size</th></tr>{rows}</table>'
         if rows else '<div class="empty">No open positions — bot is flat (between signals).</div>')
left += '</div>'
st.markdown(left, unsafe_allow_html=True)

# --- right: drawdown + yearly + fills (single grid child) ---
right = '<div class="card"><div class="card-h"><span class="t">Drawdown</span>' \
        '<span class="s">strategy</span></div>'
right += (svg_drawdown(bt[0], gid="ddc") if bt else '<div class="empty">no backtest</div>') + '</div>'
right += '<div class="card"><div class="card-h"><span class="t">Yearly Returns</span>' \
         '<span class="s">backtest</span></div>'
right += (svg_bars(yearly, gid="yrb") if yearly else '<div class="empty">no backtest</div>') + '</div>'

tr = load_trades()
if tr is not None and not tr.empty:
    trows = ""
    for _, r in tr.tail(7).iterrows():
        side = str(r.get("side", "")).upper()
        sc = UP if side == "BUY" else DOWN
        trows += (f'<tr><td class="mono">{r.get("symbol","")}</td>'
                  f'<td class="mono" style="color:{sc}">{side}</td>'
                  f'<td class="mono" style="text-align:right">{r.get("qty",0):,}</td>'
                  f'<td class="mono" style="text-align:right">{r.get("price",0):.2f}</td></tr>')
    right += (f'<div class="card"><div class="card-h"><span class="t">Recent Fills</span></div>'
              f'<table class="t"><tr><th>Symbol</th><th>Side</th>'
              f'<th style="text-align:right">Qty</th><th style="text-align:right">Price</th></tr>'
              f'{trows}</table></div>')
st.markdown(right, unsafe_allow_html=True)

st.markdown('</div>', unsafe_allow_html=True)  # close grid2


# ---------------------------------------------------------------------------
# sidebar (actions only)
# ---------------------------------------------------------------------------
st.sidebar.markdown(f'<div class="sb" style="font-weight:800;font-size:16px;'
                    f'letter-spacing:2px;color:{ACCENT}">QUASAR</div>', unsafe_allow_html=True)
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
