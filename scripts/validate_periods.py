import sys; sys.path.insert(0, "src")
import pandas as pd, numpy as np
from quasar.config import load_config
from quasar.data.feed import YFinanceFeed
from quasar.strategies.futures import FuturesEnsembleStrategy
from quasar.backtest.engine import BacktestEngine

cfg = load_config(); cf = cfg.get("costs_futures", {})
inds = ["^NSEI", "^NSEBANK"]
feed = YFinanceFeed()
data = feed.history(inds, "2014-01-01", "2026-12-31")
close = pd.DataFrame({s: data[s]["Close"] for s in inds}).sort_index().ffill().bfill()
TODAY = close.index[-1]

eng_par = dict(futures=True, max_leverage=2.0, account_dd=0.25, stop_pct=0.10)
def run(ma, start="2014-01-01", end=None):
    end = end or TODAY
    s = FuturesEnsembleStrategy(instruments=inds, ma_window=ma, trend_ma=200, strength_band=0.03,
                                primary_gate=True, instr_vol=0.10, max_leverage=2.0, long_only=False)
    w = s.run(close.loc[start:end], pd.DataFrame(index=close.loc[start:end].index,
               columns=close.columns))
    e = BacktestEngine(1e6,0,0,0,0); e.cost_pct = cf.get("cost_pct",0.0007)
    return e.run(w, close.loc[start:end], **eng_par).equity

def md(eq, s, e):
    sl = eq.loc[s:e]
    if len(sl) < 5: return float('nan'), float('nan'), float('nan')
    yrs = max((sl.index[-1]-sl.index[0]).days/365.25, 1e-9)
    cg = (sl.iloc[-1]/sl.iloc[0])**(1/yrs)-1
    d = sl.pct_change().dropna(); sh = d.mean()/(d.std()+1e-12)*np.sqrt(252)
    dd = (sl/sl.cummax()-1).min()
    return cg*100, sh, dd*100

def pct(eq, s, e):
    try: return (eq.loc[:e].iloc[-1]/eq.loc[:s].iloc[-1]-1)*100
    except: return float('nan')

print("="*78)
print("A. FULL BACKTEST (current params ma=75), 2016-2024 + through TODAY")
print("="*78)
eq = run(75)
c9,s9,d9 = md(eq,"2016-01-01","2024-12-31")
cT,sT,dT = md(eq,"2016-01-01",TODAY)
print(f"  2016-2024: CAGR {c9:5.1f}%  Sharpe {s9:4.2f}  DD {d9:6.1f}%")
print(f"  2016-TODAY: CAGR {cT:5.1f}%  Sharpe {sT:4.2f}  DD {dT:6.1f}%   final eq Rs {eq.iloc[-1]:,.0f}")

print("\n" + "="*78)
print("B. YEAR-BY-YEAR RETURNS (did it make money most years? shock-proof?)")
print("="*78)
print(f"  {'year':<6} {'return':>8} {'NIFTY':>8} {'note'}")
yr_ret = {}
for y in range(2015, TODAY.year+1):
    s=f"{y}-01-01"; e=f"{y}-12-31"
    if e > str(TODAY): e = str(TODAY)
    r = pct(eq, s, e); n = pct(close['^NSEI'], s, e)
    yr_ret[y]=r
    note=""
    if r<0 and n<0: note="DOWN-mkt, bot still -ve (but < mkt)"
    elif r>0 and n<0: note="PROFIT in down market (shock-edge WORKS)"
    elif r>0: note="up market"
    print(f"  {y:<6} {r:>7.1f}% {n:>7.1f}%  {note}")
wins = sum(1 for v in yr_ret.values() if v>0); tot=len(yr_ret)
print(f"  -> {wins}/{tot} years positive")

print("\n" + "="*78)
print("C. REGIME WINDOWS (bull / crash / bear / recent shock)")
print("="*78)
regs = [("2017 bull","2017-01-01","2017-12-31"),
        ("2020 COVID","2020-02-15","2020-04-15"),
        ("2020 recovery","2020-04-15","2020-12-31"),
        ("2021 bull","2021-01-01","2021-12-31"),
        ("2022 bear","2022-01-01","2022-12-31"),
        ("2023 chop","2023-01-01","2023-12-31"),
        ("2024 bull","2024-01-01","2024-12-31"),
        ("2025-26 YTD (today)","2025-01-01",str(TODAY)),
        ("LAST 60d (today's mkt)","2026-06-20",str(TODAY))]
for name,s,e in regs:
    r = pct(eq, s, e); n = pct(close['^NSEI'], s, e)
    print(f"  {name:<22} bot {r:>6.1f}%   NIFTY {n:>6.1f}%   {r-n:>+5.1f} alpha")

print("\n" + "="*78)
print("D. WALK-FORWARD (train picks ma, TEST is true out-of-sample)")
print("="*78)
folds = [("2014-2020 -> 2021-22","2014-01-01","2020-12-31","2021-01-01","2022-12-31"),
         ("2014-22 -> 2023-24","2014-01-01","2022-12-31","2023-01-01","2024-12-31"),
         ("2014-24 -> 2025-26","2014-01-01","2024-12-31","2025-01-01",str(TODAY))]
for lbl,trs,tre,tes,tee in folds:
    best=None
    for ma in (50,75,100):
        c,_,_ = md(run(ma,trs,tre), trs, tre)
        if best is None or c>best[1]: best=(ma,c)
    eqo = run(best[0], tes, tee)
    co,so,ddo = md(eqo, tes, tee)
    print(f"  {lbl:<24} train-best ma={best[0]} -> TEST CAGR {co:5.1f}%  Sharpe {so:4.2f}  DD {ddo:6.1f}%")
