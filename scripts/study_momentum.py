#!/usr/bin/env python3
"""Honest cross-sectional momentum on a basket of liquid Indian large-caps.
Monthly & quarterly rebalance, equal-weight long top-decile, REALISTIC Indian
delivery-equity costs (zero brokerage, STT 0.1% sell + slippage). Walk-forward
OOS = 2020-2024. This is the classic edge; test if it survives costs.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import numpy as np, pandas as pd
from quasar.data.feed import YFinanceFeed

END = "2024-12-31"
# realistic per-TRADE one-way cost for NSE delivery equity (zero brokerage):
# STT 0.1% on sell + exchange ~0.003% + slippage ~0.05%  => ~0.08% one-way.
COST_ONEWAY = 0.0008

SYMS = ["RELIANCE.NS","TCS.NS","INFY.NS","HDFCBANK.NS","ICICIBANK.NS","HINDUNILVR.NS",
        "ITC.NS","KOTAKBANK.NS","LT.NS","AXISBANK.NS","SBIN.NS","BHARTIARTL.NS",
        "ASIANPAINT.NS","MARUTI.NS","SUNPHARMA.NS","TATAMOTORS.NS","BAJFINANCE.NS",
        "WIPRO.NS","HCLTECH.NS","TATASTEEL.NS","ONGC.NS","NTPC.NS","POWERGRID.NS","TECHM.NS"]

def metrics(ret):
    eq = (1 + ret.fillna(0)).cumprod()
    yrs = (eq.index[-1] - eq.index[0]).days / 365.25
    cagr = eq.iloc[-1] ** (1 / yrs) - 1
    sharpe = ret.mean() / ret.std() * np.sqrt(12)
    dd = (eq / eq.cummax() - 1).min()
    return cagr, sharpe, dd

f = YFinanceFeed()
print("downloading", len(SYMS), "symbols...")
d = f.history(SYMS, "2013-01-01", END)
close = pd.DataFrame({s: d[s]["Close"] for s in SYMS if s in d}).sort_index().ffill().bfill()
close = close.loc[:, close.notna().sum() > 500]
print("usable symbols:", len(close.columns), "| bars:", len(close))

mret = close.resample("ME").last().pct_change()  # monthly returns
# momentum: 12-1 (return from t-12 to t-1)
mom = close.resample("ME").last().pct_change(12).shift(1)

def run(rebal_months, top_frac):
    sel = {}
    dates = mom.index[12:]
    for t in dates:
        if (list(dates).index(t) % rebal_months) != 0:
            continue
        row = mom.loc[t].dropna().sort_values(ascending=False)
        k = max(3, int(len(row) * top_frac))
        sel[t] = list(row.head(k).index)
    # portfolio monthly returns
    port = []
    prev = None
    for t in dates:
        if t in sel:
            held = sel[t]
            r = mret.loc[t, held].mean()
            # cost: turnover vs prev holdings
            if prev is None:
                to = 1.0
            else:
                keep = set(held) & set(prev)
                to = 1 - len(keep) / len(held) if held else 1.0
            cost = to * 2 * COST_ONEWAY
            r = r - cost
            prev = held
        else:
            r = port[-1] if port else 0.0  # hold
            r = mret.loc[t, prev].mean() if prev else 0.0
        port.append(r)
    port = pd.Series(port, index=dates)
    return port

oos = "2020-01-01"
print(f"\n{'config':22} | {'OOS CAGR':>9} {'Sharpe':>7} {'maxDD':>8} | {'FULL CAGR':>9}")
print("-" * 64)
for rb, tf, lbl in [(1, 0.2, "Monthly top20%"), (3, 0.2, "Quarterly top20%"),
                    (1, 0.3, "Monthly top30%"), (3, 0.3, "Quarterly top30%")]:
    p = run(rb, tf)
    c, s, dd = metrics(p)
    cf, sf, ddf = metrics(p.loc[oos:])
    print(f"{lbl:22} | {cf*100:8.1f}% {sf:7.2f} {ddf*100:7.1f}% | {c*100:8.1f}%")

# benchmark: equal-weight ALL basket buy&hold, and NIFTY
eq_all = (1 + mret.mean(axis=1).fillna(0)).cumprod()
print(f"\nEqual-wt basket B&H FULL CAGR: {metrics(eq_all.pct_change().fillna(0))[0]*100:.1f}%")
