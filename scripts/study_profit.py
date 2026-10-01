"""Profit study (focused): rank a few candidate diversified-trend configs by
full backtest + bull-capture, then validate the best with 3-fold walk-forward.
"""
import sys
sys.path.insert(0, "src")
import pandas as pd, numpy as np
from quasar.data.feed import YFinanceFeed
from quasar.strategies.futures import MultiTrendStrategy
from quasar.backtest.engine import BacktestEngine

cf = {"cost_pct": 0.0007}
feed = YFinanceFeed()
BOOKS = {
    "current": ["SPY","QQQ","IWM","EFA","EEM","INDA","TLT","IEF","GLD","SLV","DBC","USO","VNQ","XLK","GBTC"],
    "equity_heavy": ["SPY","QQQ","IWM","EFA","EEM","INDA","XLK","VNQ","GLD","SLV","GBTC","EWJ","KWEB","ARKK","XLE","XLF","HYG","TLT"],
    "risk_gold": ["SPY","QQQ","IWM","EFA","EEM","INDA","XLK","VNQ","GLD","SLV","GBTC","EWJ","KWEB","ARKK","XLE","XLF","HYG"],
}
data = feed.history([s for v in BOOKS.values() for s in v], "2014-01-01", "2026-12-31")
BOOKC = {k: [s for s in v if s in data] for k, v in BOOKS.items()}
CLOSE = {k: pd.DataFrame({s: data[s]["Close"] for s in v}).sort_index().ffill().bfill() for k, v in BOOKC.items()}
TODAY = min(c.index[-1] for c in CLOSE.values())
print("Books:", {k: len(v) for k, v in BOOKC.items()}, "| TODAY", TODAY.date())
eng_par = dict(futures=True, max_leverage=2.0, account_dd=0.25, stop_pct=0.10)

def run(book, ma, pv, gc, gate, long_gate=None, short_gate=None):
    close = CLOSE[book]
    s = MultiTrendStrategy(instruments=BOOKC[book], ma_window=ma, trend_ma=200,
                           strength_band=0.03, primary_gate=gate, instr_vol=0.10,
                           portfolio_vol=pv, max_leverage=2.0, gross_cap=gc,
                           vol_window=20, long_only=False,
                           long_gate=long_gate, short_gate=short_gate)
    w = s.run(close, pd.DataFrame(index=close.index, columns=close.columns))
    e = BacktestEngine(1e6, 0, 0, 0, 0); e.cost_pct = cf["cost_pct"]
    return e.run(w, close, **eng_par).equity

def md(eq, s, e):
    sl = eq.loc[s:e]
    if len(sl) < 5: return float("nan"), float("nan"), float("nan")
    yrs = max((sl.index[-1]-sl.index[0]).days/365.25, 1e-9)
    cg = (sl.iloc[-1]/sl.iloc[0])**(1/yrs)-1
    d = sl.pct_change().dropna(); sh = d.mean()/(d.std()+1e-12)*np.sqrt(252)
    dd = (sl/sl.cummax()-1).min()
    return cg*100, sh, dd*100

def pct(eq, s, e):
    try: return (eq.loc[:e].iloc[-1]/eq.loc[:s].iloc[-1]-1)*100
    except: return float("nan")

BULL = [2017, 2019, 2021, 2023, 2024, 2025]
def bull_alpha(eq, spy):
    return np.mean([pct(eq, f"{y}-01-01", f"{y}-12-31") - pct(spy, f"{y}-01-01", f"{y}-12-31") for y in BULL])

folds = [("14-20->21-22","2014-01-01","2020-12-31","2021-01-01","2022-12-31"),
         ("14-22->23-24","2014-01-01","2022-12-31","2023-01-01","2024-12-31"),
         ("14-24->25-26","2014-01-01","2024-12-31","2025-01-01",str(TODAY))]

CAND = [
    ("current", 100, 0.10, 3.0, True,  None, None, "BASELINE"),
    ("current", 100, 0.15, 4.0, False, None, None, "cur-gateF"),
    ("current", 100, 0.15, 4.0, False, False, True, "ASYM-lFast-sConf"),
    ("current", 75,  0.15, 4.0, False, False, True, "ASYM-ma75"),
    ("current", 75,  0.18, 5.0, False, False, True, "ASYM-ma75-agg"),
    ("current", 100, 0.18, 5.0, False, False, True, "ASYM-ma100-agg"),
]
print("\n=== FULL + REGIME ===")
res = []
for book, ma, pv, gc, gate, lg, sg, lbl in CAND:
    spy = CLOSE[book]["SPY"]
    eq = run(book, ma, pv, gc, gate, lg, sg)
    cT, sT, dT = md(eq, "2016-01-01", str(TODAY))
    ba = bull_alpha(eq, spy)
    last60 = pct(eq, "2026-06-20", str(TODAY))
    crash = pct(eq, "2020-02-15", "2020-04-15")
    y22 = pct(eq, "2022-01-01", "2022-12-31")
    res.append((lbl, book, ma, pv, gc, gate, cT, sT, dT, ba, last60, crash, y22))
    print(f"{lbl:<16} ma{ma} pv{pv} gc{gc} | "
          f"CAGR {cT:5.1f} Sh {sT:4.2f} DD {dT:6.1f} | bullA {ba:5.1f} last60 {last60:5.1f} crash {crash:5.1f} 2022 {y22:5.1f}")

print("\n=== WALK-FORWARD (all candidates) ===")
for lbl, book, ma, pv, gc, gate, *_ in res:
    wf = []
    for _, trs, tre, tes, tee in folds:
        best = None
        for tma in (50, 75, 100):
            for tgp in (3.0, 4.0, 5.0):
                c, _, _ = md(run(book, tma, tgp, 0.15, False, False, True), trs, tre)
                if best is None or c > best[2]: best = (tma, tgp, c)
        co, _, _ = md(run(book, best[0], best[1], 0.15, False, False, True), tes, tee)
        wf.append(co)
    print(f"{lbl:<16} | WF {[round(x,1) for x in wf]} | all+? {'YES' if all(x>0 for x in wf) else 'NO'}")
