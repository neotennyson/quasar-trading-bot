import sys; sys.path.insert(0, "src")
import pandas as pd, numpy as np
from quasar.config import load_config
from quasar.data.feed import YFinanceFeed
from quasar.strategies.futures import MultiTrendStrategy
from quasar.backtest.engine import BacktestEngine

cfg = load_config(); cf = cfg.get("costs_futures", {})
# Diversified, UNCORRELATED multi-asset book (liquid, long history on yfinance).
# This is what real CTAs trade; it's the universe - not the signal - that creates
# robust trend profit. INDA proxies NIFTY so India exposure is still in the book.
UNI = ["SPY","QQQ","IWM","EFA","EEM","INDA","TLT","IEF","GLD","SLV","DBC","USO","VNQ","XLK","GBTC"]
feed = YFinanceFeed()
data = feed.history(UNI, "2014-01-01", "2026-12-31")
avail = [s for s in UNI if s in data]
close = pd.DataFrame({s: data[s]["Close"] for s in avail}).sort_index().ffill().bfill()
print(f"Diversified book ({len(avail)} assets): {avail}")
TODAY = close.index[-1]
eng_par = dict(futures=True, max_leverage=2.0, account_dd=0.25, stop_pct=0.10)

def run(ma, gp=4.0, start="2014-01-01", end=None):
    end = end or TODAY
    s = MultiTrendStrategy(instruments=avail, ma_window=ma, trend_ma=200, strength_band=0.03,
                           primary_gate=True, instr_vol=0.10, portfolio_vol=0.15,
                           max_leverage=2.0, gross_cap=gp, vol_window=20, long_only=False)
    w = s.run(close.loc[start:end], pd.DataFrame(index=close.loc[start:end].index, columns=close.columns))
    e = BacktestEngine(1e6,0,0,0,0); e.cost_pct = cf.get("cost_pct",0.0007)
    return e.run(w, close.loc[start:end], **eng_par).equity

def md(eq,s,e):
    sl=eq.loc[s:e]
    if len(sl)<5: return float('nan'),float('nan'),float('nan')
    yrs=max((sl.index[-1]-sl.index[0]).days/365.25,1e-9)
    cg=(sl.iloc[-1]/sl.iloc[0])**(1/yrs)-1; d=sl.pct_change().dropna()
    sh=d.mean()/(d.std()+1e-12)*np.sqrt(252); dd=(sl/sl.cummax()-1).min()
    return cg*100,sh,dd*100
def pct(eq,s,e):
    try: return (eq.loc[:e].iloc[-1]/eq.loc[:s].iloc[-1]-1)*100
    except: return float('nan')

print("\nA. FULL (ma=75, gross_cap=4): 2016-2024 + through TODAY (vs SPY buy-hold)")
c9,s9,d9=md(run(75),"2016-01-01","2024-12-31")
cT,sT,dT=md(run(75),"2016-01-01",TODAY)
print(f"  2016-2024: CAGR {c9:5.1f}%  Sharpe {s9:4.2f}  DD {d9:6.1f}%")
print(f"  2016-TODAY: CAGR {cT:5.1f}%  Sharpe {sT:4.2f}  DD {dT:6.1f}%")
sp_full=pct(close['SPY'],"2016-01-01",TODAY)
print(f"  SPY buy-hold 2016-TODAY: {sp_full:+.1f}%  -> strategy alpha vs SPY: {cT-sp_full:+.1f}%")

print("\nB. YEAR-BY-YEAR")
for y in range(2015,TODAY.year+1):
    s=f"{y}-01-01"; e=f"{y}-12-31"
    if e>str(TODAY): e=str(TODAY)
    r=pct(run(75),s,e); n=pct(close['SPY'],s,e)
    print(f"  {y}: bot {r:>6.1f}%  SPY {n:>6.1f}%  {r-n:>+5.1f}")
eq=run(75)
yrs_pos=sum(1 for y in range(2015,TODAY.year+1) if pct(eq,f"{y}-01-01",f"{y}-12-31" if f"{y}-12-31"<=str(TODAY) else str(TODAY))>0)
print(f"  -> {yrs_pos}/{TODAY.year-2015+1} years positive")

print("\nC. REGIMES (incl TODAY)")
for name,s,e in [("2020 COVID","2020-02-15","2020-04-15"),("2022 bear","2022-01-01","2022-12-31"),
                 ("2024 bull","2024-01-01","2024-12-31"),("2025-26 YTD","2025-01-01",str(TODAY)),
                 ("LAST 60d","2026-06-20",str(TODAY))]:
    r=pct(eq,s,e); n=pct(close['SPY'],s,e); ni=pct(close['INDA'],s,e)
    print(f"  {name:<14} bot {r:>6.1f}%  SPY {n:>6.1f}%  INDA {ni:>6.1f}%")

print("\nD. WALK-FORWARD (train picks ma+gross_cap, TEST unseen)")
folds=[("14-20->21-22","2014-01-01","2020-12-31","2021-01-01","2022-12-31"),
       ("14-22->23-24","2014-01-01","2022-12-31","2023-01-01","2024-12-31"),
       ("14-24->25-26","2014-01-01","2024-12-31","2025-01-01",str(TODAY))]
allpos=True
for lbl,trs,tre,tes,tee in folds:
    best=None
    for ma in (50,75,100):
        for gp in (3.0,4.0,5.0):
            c,_,_=md(run(ma,gp,trs,tre),trs,tre)
            if best is None or c>best[2]: best=(ma,gp,c)
    co,so,ddo=md(run(best[0],best[1],tes,tee),tes,tee)
    if co<=0: allpos=False
    print(f"  {lbl:<14} train ma={best[0]} gp={best[1]:.0f} -> TEST CAGR {co:5.1f}%  Sharpe {so:4.2f}  DD {ddo:6.1f}%")
print(f"\n  ALL walk-forward folds positive? {'YES' if allpos else 'NO'}")
