#!/usr/bin/env python3
"""QUASAR final validation: Index Trend + vol targeting vs buy & hold."""
from __future__ import annotations
import logging, os, sys
import pandas as pd
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from quasar.config import load_config
from quasar.data.feed import YFinanceFeed
from quasar.strategies.trend import IndexTrendStrategy
from quasar.risk.manager import RiskManager
from quasar.backtest.engine import BacktestEngine

logging.disable(logging.CRITICAL)
cfg = load_config()
feed = YFinanceFeed()
start, end = cfg.get("backtest.start"), cfg.get("backtest.end")
syms = list(dict.fromkeys(["^NSEI", "NIFTYBEES.NS"] + cfg.get("universe.symbols")))
data = feed.history(syms, start, end)
close = pd.DataFrame({s: data[s]["Close"] for s in syms if s in data}).sort_index()
close = close.loc[:, ~close.columns.duplicated()]
bench = close["^NSEI"]
cap = cfg.get("backtest.initial_capital")

def run(strat, label, cost=0.00175):
    w = strat.run(close, pd.DataFrame(index=close.index, columns=close.columns, data=0.0))
    risk = RiskManager(max_positions=1, max_weight=2.0, cash_buffer=0.0,
                       stop_loss_pct=0.0, target_drawdown_pct=0.5)
    eng = BacktestEngine(initial_capital=cap, commission_pct=0, stt_pct=0,
                         slippage_pct=0, impact_pct=0, stop_loss_pct=0.0)
    eng.cost_pct = cost
    r = eng.run(w, close, risk_mgr=risk, benchmark=bench)
    m = r.metrics
    print(f"{label:40s} ret={m['total_return']*100:7.1f}% cagr={m['cagr']*100:6.1f}% "
          f"sharpe={m['sharpe']:.2f} mdd={m['max_drawdown']*100:6.1f}% vol={m['volatility']*100:5.1f}%")

print("=== QUASAR FINAL VALIDATION (cost ~0.18%/turnover) ===")
run(IndexTrendStrategy(mode="above_ma", ma_window=50, vol_target=0.15, max_leverage=1.5),
    "QUASAR above_ma50 + volTgt 15%")
run(IndexTrendStrategy(mode="above_ma", ma_window=50, vol_target=0.12, max_leverage=1.5),
    "QUASAR above_ma50 + volTgt 12%")
run(IndexTrendStrategy(mode="cross", fast=20, slow=50, vol_target=0.15, max_leverage=1.5),
    "QUASAR cross 20/50 + volTgt 15%")
run(IndexTrendStrategy(mode="above_ma", ma_window=50, vol_target=0.0, max_leverage=1.0),
    "QUASAR above_ma50 NO leverage")

eng = BacktestEngine(initial_capital=cap)
bh = eng.run(pd.DataFrame({"^NSEI": 1.0}, index=close.index), close, benchmark=bench)
mb = bh.metrics
print(f"{'BUY&HOLD Nifty':40s} ret={mb['total_return']*100:7.1f}% cagr={mb['cagr']*100:6.1f}% "
      f"sharpe={mb['sharpe']:.2f} mdd={mb['max_drawdown']*100:6.1f}% vol={mb['volatility']*100:5.1f}%")
