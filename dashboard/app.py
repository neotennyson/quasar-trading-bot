"""QUASAR dashboard (Streamlit).

A clean single-page view of the bot's health:
  - Backtest equity curve + drawdown + KPIs
  - Live paper book (cash, positions, equity) from state.json
  - Current per-instrument signals (long / flat / short)
  - Recent trades
  - Strategy configuration

Run:  streamlit run dashboard/app.py
"""
from __future__ import annotations
import os
import sys
import subprocess
import pandas as pd
import numpy as np
import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from quasar.config import load_config

ROOT = os.path.dirname(__file__)


def load_backtest():
    p = os.path.join(ROOT, "data", "equity_curve.csv")
    if not os.path.exists(p):
        return None
    eq = pd.read_csv(p, index_col=0, parse_dates=True).iloc[:, 0]
    ret = eq.iloc[-1] / eq.iloc[0] - 1
    n_years = max((eq.index[-1] - eq.index[0]).days / 365.25, 1e-9)
    cagr = (eq.iloc[-1] / eq.iloc[0]) ** (1 / n_years) - 1
    dret = eq.pct_change().dropna()
    sharpe = dret.mean() / (dret.std() + 1e-12) * np.sqrt(252)
    dd = (eq / eq.cummax() - 1).min()
    return eq, dict(ret=ret, cagr=cagr, sharpe=sharpe, dd=dd, final=float(eq.iloc[-1]))


def load_state():
    p = os.path.join(ROOT, "data", "state.json")
    if not os.path.exists(p):
        return None
    import json
    return json.load(open(p))


def load_trades():
    p = os.path.join(ROOT, "data", "trades.csv")
    if not os.path.exists(p):
        return None
    return pd.read_csv(p)


def run_paper_step():
    subprocess.run([sys.executable, "-m", "quasar.paper.trader", "--once"],
                   cwd=ROOT, env={**os.environ, "PYTHONPATH": os.path.join(ROOT, "src")},
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main():
    st.set_page_config(page_title="QUASAR", layout="wide")
    cfg = load_config()
    active = cfg.get("strategy.active")
    broker = cfg.get("broker.mode", "paper")

    st.title("QUASAR · Automated F&O Trader")
    st.caption(f"Active strategy: **{active}**  ·  Broker mode: **{broker}**  ·  "
               f"Goal: make money across every opportunity")

    bt = load_backtest()
    state = load_state()

    # ---- KPI row ----
    c1, c2, c3, c4, c5 = st.columns(5)
    if bt:
        c1.metric("Backtest Return", f"{bt[1]['ret']*100:.1f}%")
        c2.metric("Backtest CAGR", f"{bt[1]['cagr']*100:.1f}%")
        c3.metric("Backtest Sharpe", f"{bt[1]['sharpe']:.2f}")
        c4.metric("Backtest MaxDD", f"{bt[1]['dd']*100:.1f}%")
    else:
        for c in (c1, c2, c3, c4):
            c.metric("Backtest", "run backtest")
    paper_eq = None
    if state and state.get("equity_curve"):
        paper_eq = state["equity_curve"][-1]["equity"]
    c5.metric("Paper Equity", f"₹{paper_eq:,.0f}" if paper_eq else "—")

    # ---- Equity + drawdown ----
    if bt:
        eq = bt[0]
        col_l, col_r = st.columns(2)
        with col_l:
            st.subheader("Backtest Equity Curve")
            st.line_chart(eq)
        with col_r:
            st.subheader("Backtest Drawdown")
            dd = eq / eq.cummax() - 1
            st.area_chart(dd)

    # ---- Current signals ----
    st.subheader("Current Signals (per instrument)")
    if state and state.get("last_signal"):
        sig = pd.DataFrame(
            [{"Instrument": k, "Weight": round(v, 3),
              "Action": "LONG" if v > 0 else ("SHORT" if v < 0 else "FLAT")}
             for k, v in state["last_signal"].items() if v != 0]
        ).sort_values("Weight", key=lambda s: s.abs(), ascending=False)
        if sig.empty:
            st.info("No open positions — bot is flat (trend down / between signals).")
        else:
            st.dataframe(sig, use_container_width=True, height=320)
    else:
        st.info("No signal yet — run a paper step or backtest first.")

    # ---- Paper book ----
    st.subheader("Paper Book")
    if state:
        col_a, col_b = st.columns(2)
        col_a.metric("Cash", f"₹{state.get('cash', 0):,.0f}")
        col_a.metric("Open Positions", len(state.get("shares", {})))
        if state.get("equity_curve"):
            peq = pd.Series({x["date"]: x["equity"] for x in state["equity_curve"]})
            col_b.line_chart(peq)
    else:
        st.info("No paper state — run a paper step.")

    # ---- Trades ----
    st.subheader("Recent Trades")
    tr = load_trades()
    if tr is not None and not tr.empty:
        st.dataframe(tr.tail(20), use_container_width=True)
    else:
        st.info("No trades logged yet.")

    # ---- Config ----
    with st.expander("Strategy Configuration"):
        st.json(cfg.get("strategy", {}))
        st.json(cfg.get("costs_futures", {}))

    # ---- Actions ----
    st.sidebar.title("Actions")
    if st.sidebar.button("Run paper step (refresh signals)"):
        with st.spinner("Fetching latest data + computing signals..."):
            run_paper_step()
        st.rerun()
    if st.sidebar.button("Re-run full backtest"):
        with st.spinner("Running backtest (may take a few minutes)..."):
            subprocess.run([sys.executable, "scripts/backtest.py", "--save"],
                           cwd=ROOT, env={**os.environ, "PYTHONPATH": os.path.join(ROOT, "src")},
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        st.rerun()

    # ---- Footer ----
    st.divider()
    st.caption("QUASAR · powered by Hy3")


if __name__ == "__main__":
    main()
