#!/usr/bin/env python3
"""Rigorous walk-forward validation of cross-sectional 12-1 momentum on a BROAD
basket of liquid Indian stocks, with REALISTIC F&O execution costs (stock
futures: STT 0.02% sell + brokerage + slippage + monthly roll). Reports full
CAGR, rolling 3y OOS segments, and buy-and-hold benchmark. No parameter fitting.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import numpy as np, pandas as pd
from quasar.data.feed import YFinanceFeed

END = "2024-12-31"
# realistic stock-FUTURES round-trip cost per rebalance (applied to turnover):
# STT 0.02% sell + brokerage 0.02% + slippage 0.05% + roll 0.08%  ~= 0.17% RT
COST_RT = 0.0017

# broad liquid large/mid-cap list (reduces single-name survivorship)
SYMS = ["RELIANCE.NS","TCS.NS","INFY.NS","HDFCBANK.NS","ICICIBANK.NS","HINDUNILVR.NS",
        "ITC.NS","KOTAKBANK.NS","LT.NS","AXISBANK.NS","SBIN.NS","BHARTIARTL.NS",
        "ASIANPAINT.NS","MARUTI.NS","SUNPHARMA.NS","TATAMOTORS.NS","BAJFINANCE.NS",
        "WIPRO.NS","HCLTECH.NS","TATASTEEL.NS","ONGC.NS","NTPC.NS","POWERGRID.NS",
        "TECHM.NS","TITAN.NS","ULTRACEMCO.NS","ADANIPORTS.NS","BAJAJFINSV.NS",
        "GRASIM.NS","CIPLA.NS","DRREDDY.NS","EICHERMOT.NS","HEROMOTOCO.NS","JSWSTEEL.NS",
        "NESTLEIND.NS","TATACONSUM.NS","SHREECEM.NS","DIVISLAB.NS","BRITANNIA.NS","COALINDIA.NS"]

def metrics(ret):
    ret = ret.fillna(0)
    eq = (1 + ret).cumprod()
    yrs = (eq.index[-1] - eq.index[0]).days / 365.25
    cagr = eq.iloc[-1] ** (1 / yrs) - 1
    sharpe = ret.mean() / ret.std() * np.sqrt(12)
    dd = (eq / eq.cummax() - 1).min()
    return cagr, sharpe, dd

f = YFinanceFeed()
print("downloading", len(SYMS), "symbols...")
d = f.history(SYMS, "2012-01-01", END)
close = pd.DataFrame({s: d[s]["Close"] for s in SYMS if s in d}).sort_index().ffill().bfill()
close = close.loc[:, close.notna().sum() > 1000]
print("usable:", len(close.columns), "bars:", len(close))

mret = close.resample("ME").last().pct_change()
mom = close.resample("ME").last().pct_change(12).shift(1)  # 12-1 momentum

# monthly rebalance, equal-weight top 1/3 by momentum (no fitting)
dates = mom.index[12:]
held = None
port = []
for t in dates:
    row = mom.loc[t].dropna().sort_values(ascending=False)
    k = max(5, int(len(row) * 1/3))
    new = list(row.head(k).index)
    r = mret.loc[t, new].mean()
    to = 1.0 if held is None else 1 - len(set(new) & set(held)) / len(new)
    r = r - to * COST_RT
    port.append(r); held = new
port = pd.Series(port, index=dates)

c, s, dd = metrics(port)
print(f"\nMomentum (top1/3, monthly, F&O costs) FULL: CAGR {c*100:.1f}%  Sharpe {s:.2f}  maxDD {dd*100:.1f}%")

# rolling 3y OOS segments
print("\nRolling 3-year OOS segments (CAGR | Sharpe | maxDD):")
for y0 in range(2015, 2022):
    seg = port.loc[f"{y0}-01-01":f"{y0+3}-12-31"]
    if len(seg) > 20:
        cc, ss, ddc = metrics(seg)
        # benchmark NIFTY over same window
        print(f"  {y0}-{y0+3}: {cc*100:6.1f}% | {ss:5.2f} | {ddc*100:6.1f}%")

# benchmark: equal-weight basket buy & hold (cash proxy) full
bh = (1 + mret.mean(axis=1).fillna(0)).cumprod()
cb, sb, ddb = metrics(bh.pct_change().fillna(0))
print(f"\nEqual-wt basket B&H FULL: CAGR {cb*100:.1f}%  Sharpe {sb:.2f}  maxDD {ddb*100:.1f}%")
# NIFTY B&H
nx = f.history(["^NSEI"], "2012-01-01", END)["^NSEI"]["Close"].dropna().resample("ME").last().pct_change()
cn, sn, dn = metrics(nx.fillna(0))
print(f"NIFTY B&H FULL:           CAGR {cn*100:.1f}%  Sharpe {sn:.2f}  maxDD {dn*100:.1f}%")
