#!/usr/bin/env python3
"""Sweep index-timing (close-to-close) rules on Nifty. Pick the best."""
from __future__ import annotations
import logging, os, sys
import pandas as pd, numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from quasar.config import load_config
from quasar.data.feed import YFinanceFeed
from quasar.risk.manager import RiskManager
from quasar.backtest.engine import BacktestEngine

logging.disable(logging.CRITICAL)
cfg = load_config()
feed = YFinanceFeed()
start, end = cfg.get("backtest.start"), cfg.get("backtest.end")
data = feed.history(["^NSEI", "NIFTYBEES.NS"], start, end)
close = pd.DataFrame({s: data[s]["Close"] for s in ["^NSEI", "NIFTYBEES.NS"] if s in data}).sort_index()
close = close.loc[:, ~close.columns.duplicated()]
idx = "^NSEI"
px = close[idx]
bench = px

risk = RiskManager(max_positions=1, max_weight=1.0, cash_buffer=0.0, stop_loss_pct=0.0, target_drawdown_pct=0.5)
eng = BacktestEngine(initial_capital=cfg.get("backtest.initial_capital"),
                     commission_pct=0.0, stt_pct=0.0, slippage_pct=0.0, impact_pct=0.0, stop_loss_pct=0.0)
eng.cost_pct = 0.002  # ~0.2% round-trip on flips

def backtest(weight_series, label):
    w = pd.DataFrame({idx: weight_series}, index=close.index)
    r = eng.run(w, close, risk_mgr=risk, benchmark=bench)
    m = r.metrics
    print(f"{label:34s} ret={m['total_return']*100:7.1f}% cagr={m['cagr']*100:6.1f}% "
          f"sharpe={m['sharpe']:.2f} mdd={m['max_drawdown']*100:6.1f}% vol={m['volatility']*100:5.1f}%")

print("=== INDEX TIMING SWEEP (Nifty, cost ~0.2%/flip) ===")
for fast, slow in [(20,50),(50,100),(50,200),(100,200),(20,200),(10,100),(30,150)]:
    f = px.rolling(fast).mean(); s = px.rolling(slow).mean()
    backtest((f >= s).astype(float), f"MA cross {fast}/{slow}")

for w in [50,100,150,200]:
    ma = px.rolling(w).mean()
    backtest((px >= ma).astype(float), f"Above MA {w}")

m12 = px / px.shift(252) - 1
backtest((m12 > 0).astype(float).fillna(0), "12-mo return > 0")
backtest((m12 > 0.05).astype(float).fillna(0), "12-mo return > 5%")

# buy & hold
bh = eng.run(pd.DataFrame({idx: 1.0}, index=close.index), close, benchmark=bench)
mb = bh.metrics
print(f"{'BUY&HOLD Nifty':34s} ret={mb['total_return']*100:7.1f}% cagr={mb['cagr']*100:6.1f}% "
      f"sharpe={mb['sharpe']:.2f} mdd={mb['max_drawdown']*100:6.1f}% vol={mb['volatility']*100:5.1f}%")
