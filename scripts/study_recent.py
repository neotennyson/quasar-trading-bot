"""Recent-regime tuning: find a diversified-trend variant that survives the
choppy 2025-26 window WITHOUT breaking full-period robustness / walk-forward.
"""
import sys
sys.path.insert(0, "src")
import pandas as pd, numpy as np
from quasar.data.feed import YFinanceFeed
from quasar.strategies.futures import MultiTrendStrategy, FuturesEnsembleStrategy
from quasar.backtest.engine import BacktestEngine

cf = {"cost_pct": 0.0007}
feed = YFinanceFeed()
BOOK = ["SPY","QQQ","IWM","EFA","EEM","INDA","TLT","IEF","GLD","SLV","DBC","USO","VNQ","XLK","GBTC"]
data = feed.history(BOOK, "2014-01-01", "2026-12-31")
close = pd.DataFrame({s: data[s]["Close"] for s in BOOK if s in data}).sort_index().ffill().bfill()
TODAY = close.index[-1]
print("Book:", len(BOOK), "TODAY", TODAY.date())
eng_par = dict(futures=True, max_leverage=2.0, account_dd=0.25, stop_pct=0.10)

def scale_portfolio(raw, portfolio_vol, gross_cap, max_lev, vol_window=20):
    lo = -max_lev
    asset_ret = close.pct_change().fillna(0.0)
    rp = (raw * asset_ret).sum(axis=1)
    rp_vol = rp.rolling(vol_window).std() * np.sqrt(252)
    sc = (portfolio_vol / rp_vol).fillna(0.0)
    w = raw.mul(sc, axis=0).clip(lo, max_lev)
    gross = w.abs().sum(axis=1)
    div = (gross / gross_cap).where(gross > gross_cap, 1.0)
    return w.divide(div, axis=0).fillna(0.0)

def run_mt(ma, sb, pv=0.18, gc=5.0):
    s = MultiTrendStrategy(instruments=BOOK, ma_window=ma, trend_ma=200, strength_band=sb,
                           primary_gate=False, long_gate=False, short_gate=True,
                           instr_vol=0.10, portfolio_vol=pv, max_leverage=2.0, gross_cap=gc,
                           vol_window=20, long_only=False)
    w = s.run(close, pd.DataFrame(index=close.index, columns=close.columns))
    e = BacktestEngine(1e6,0,0,0,0); e.cost_pct=cf["cost_pct"]
    return e.run(w, close, **eng_par).equity

def run_ens(pv=0.18, gc=5.0, wb=1.0, wbo=1.0, wt=1.0):
    s = FuturesEnsembleStrategy(instruments=BOOK, ma_window=75, trend_ma=200, strength_band=0.03,
                                primary_gate=False, instr_vol=0.10, max_leverage=2.0, vol_window=20,
                                long_only=False, w_trend=wt, w_boll=wb, w_breakout=wbo,
                                boll_k=20, boll_std=2.0, breakout_n=20)
    raw = s.run(close, pd.DataFrame(index=close.index, columns=close.columns))
    w = scale_portfolio(raw, pv, gc, 2.0)
    e = BacktestEngine(1e6,0,0,0,0); e.cost_pct=cf["cost_pct"]
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

folds = [("14-20->21-22","2014-01-01","2020-12-31","2021-01-01","2022-12-31"),
         ("14-22->23-24","2014-01-01","2022-12-31","2023-01-01","2024-12-31"),
         ("14-24->25-26","2014-01-01","2024-12-31","2025-01-01",str(TODAY))]
def wf_ok(eq_factory):
    ok = True; vals = []
    for _, trs, tre, tes, tee in folds:
        c,_,_ = md(eq_factory(), tes, tee); vals.append(c)
        if c <= 0: ok = False
    return ok, vals

CAND = []
print("\n=== MULTI-TREND (asym) variants ===")
for ma in (50, 75, 100):
    for sb in (0.03, 0.05, 0.07):
        eq = run_mt(ma, sb)
        cT, sT, dT = md(eq, "2016-01-01", str(TODAY))
        r2526 = pct(eq, "2025-01-01", str(TODAY))
        last60 = pct(eq, "2026-06-20", str(TODAY))
        ok, wfv = wf_ok(lambda: run_mt(ma, sb))
        score = cT*0.4 + r2526*0.4 + last60*0.2
        CAND.append((f"MT ma{ma} sb{sb}", cT, sT, dT, r2526, last60, ok, wfv, score))
        print(f"MT ma{ma} sb{sb:<4} | CAGR {cT:5.1f} Sh {sT:4.2f} DD {dT:6.1f} | 25-26 {r2526:5.1f} last60 {last60:5.1f} | WF {[round(x,1) for x in wfv]} {'OK' if ok else 'NO'}")

print("\n=== ENSEMBLE (trend+boll+breakout) blends ===")
for wb, wbo in [(1,1),(1,2),(2,1),(0.5,2)]:
    eq = run_ens(wb=wb, wbo=wbo)
    cT, sT, dT = md(eq, "2016-01-01", str(TODAY))
    r2526 = pct(eq, "2025-01-01", str(TODAY))
    last60 = pct(eq, "2026-06-20", str(TODAY))
    ok, wfv = wf_ok(lambda: run_ens(wb=wb, wbo=wbo))
    score = cT*0.4 + r2526*0.4 + last60*0.2
    CAND.append((f"ENS b{wb} bo{wbo}", cT, sT, dT, r2526, last60, ok, wfv, score))
    print(f"ENS b{wb} bo{wbo} | CAGR {cT:5.1f} Sh {sT:4.2f} DD {dT:6.1f} | 25-26 {r2526:5.1f} last60 {last60:5.1f} | WF {[round(x,1) for x in wfv]} {'OK' if ok else 'NO'}")

print("\n=== RANKED (recent-aware score) ===")
for r in sorted(CAND, key=lambda x: x[8], reverse=True):
    print(f"{r[0]:<14} CAGR {r[1]:5.1f} Sh {r[2]:4.2f} DD {r[3]:6.1f} 25-26 {r[4]:5.1f} last60 {r[5]:5.1f} WFok {r[6]}")
