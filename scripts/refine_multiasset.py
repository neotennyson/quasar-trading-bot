import sys; sys.path.insert(0, "src")
import pandas as pd, numpy as np
from quasar.data.feed import YFinanceFeed
from quasar.strategies.futures import MultiTrendStrategy
from quasar.backtest.engine import BacktestEngine

UNI=["SPY","QQQ","IWM","EFA","EEM","INDA","TLT","IEF","GLD","SLV","DBC","USO","VNQ","XLK","GBTC"]
feed=YFinanceFeed(); data=feed.history(UNI,"2014-01-01","2026-12-31")
avail=[s for s in UNI if s in data]
close=pd.DataFrame({s:data[s]["Close"] for s in avail}).sort_index().ffill().bfill()
TODAY=close.index[-1]
def run(ma,pv,gc,start="2014-01-01",end=None):
    end=end or TODAY
    s=MultiTrendStrategy(instruments=avail,ma_window=ma,trend_ma=200,strength_band=0.03,
        primary_gate=True,instr_vol=0.10,portfolio_vol=pv,max_leverage=2.0,gross_cap=gc,vol_window=20,long_only=False)
    w=s.run(close.loc[start:end],pd.DataFrame(index=close.loc[start:end].index,columns=close.columns))
    e=BacktestEngine(1e6,0,0,0,0); e.cost_pct=0.0007
    return e.run(w,close.loc[start:end],futures=True,max_leverage=2.0,account_dd=0.25,stop_pct=0.10).equity
def md(eq,s,e):
    sl=eq.loc[s:e]
    if len(sl)<5: return float('nan'),float('nan'),float('nan')
    yrs=max((sl.index[-1]-sl.index[0]).days/365.25,1e-9)
    cg=(sl.iloc[-1]/sl.iloc[0])**(1/yrs)-1; d=sl.pct_change().dropna()
    return cg*100,d.mean()/(d.std()+1e-12)*np.sqrt(252),(sl/sl.cummax()-1).min()*100
folds=[("14-20->21-22","2014-01-01","2020-12-31","2021-01-01","2022-12-31"),
       ("14-22->23-24","2014-01-01","2022-12-31","2023-01-01","2024-12-31"),
       ("14-24->25-26","2014-01-01","2024-12-31","2025-01-01",str(TODAY))]
print(f"{'config(ma=100)':<22} | {'FULL CAGR':>9} {'DD':>6} | WF1   WF2   WF3   | all+?")
for pv,gc in [(0.15,4.0),(0.12,3.0),(0.10,3.0),(0.12,2.0),(0.10,2.0)]:
    fc,fs,fd=md(run(100,pv,gc),"2016-01-01",TODAY)
    wfs=[]
    for lbl,trs,tre,tes,tee in folds:
        wfs.append(md(run(100,pv,gc,tes,tee),tes,tee)[0])
    allpos=all(x>0 for x in wfs)
    print(f"pv={pv} gc={gc:<4} | {fc:>8.1f}% {fd:>5.1f}% | {wfs[0]:>5.1f} {wfs[1]:>5.1f} {wfs[2]:>5.1f} | {'YES' if allpos else 'NO'}")
