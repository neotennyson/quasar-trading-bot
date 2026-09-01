#!/usr/bin/env python3
"""Experiment: index trend-following + overnight drift vs benchmark."""
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
syms = list(dict.fromkeys([cfg.get("strategy.regime_filter.index"), cfg.get("backtest.benchmark")] + cfg.get("universe.symbols")))
data = feed.history(syms, cfg.get("backtest.start"), cfg.get("backtest.end"))
close = pd.DataFrame({s: data[s]["Close"] for s in syms if s in data}).sort_index()
close = close.loc[:, ~close.columns.duplicated()]

# robust regime/benchmark symbol: try configured, else first available proxy
def _first_available(preferred, candidates):
    if preferred in close.columns:
        return preferred
    for c in candidates:
        if c in close.columns:
            return c
    return close.columns[0]

bench_sym = _first_available(cfg.get("backtest.benchmark"),
                             ["NIFTYBEES.NS", "INFY.NS", "RELIANCE.NS"])
regime_sym = _first_available(cfg.get("strategy.regime_filter.index"),
                              ["NIFTYBEES.NS", "INFY.NS", "RELIANCE.NS"])
bench = close[bench_sym]
print(f"[info] using benchmark/regime proxy = {bench_sym}")

risk = RiskManager(max_positions=1, max_weight=1.0, cash_buffer=0.0,
                   stop_loss_pct=0.0, target_drawdown_pct=0.5)
eng = BacktestEngine(initial_capital=cfg.get("backtest.initial_capital"),
                     commission_pct=cfg.get("costs.commission_pct"), stt_pct=cfg.get("costs.stt_pct"),
                     slippage_pct=cfg.get("costs.slippage_pct"), impact_pct=cfg.get("costs.impact_pct"),
                     stop_loss_pct=0.0)

def metrics_of(weights, label):
    r = eng.run(weights, close, risk_mgr=risk, benchmark=bench)
    m = r.metrics
    print(f"{label:42s} ret={m['total_return']*100:7.1f}% cagr={m['cagr']*100:6.1f}% "
          f"sharpe={m['sharpe']:.2f} mdd={m['max_drawdown']*100:6.1f}% vol={m['volatility']*100:5.1f}%")

print("== INDEX TREND FOLLOWING (NIFTYBEES, invested when price>MA) ==")
for w in [50, 100, 150, 200]:
    ma = bench.rolling(w).mean()
    w_series = (bench >= ma).astype(float)
    weights = pd.DataFrame({bench_sym: w_series}, index=close.index)
    metrics_of(weights, f"Trend MA={w}")

print("== INDEX TREND FOLLOWING (fast/slow cross 50/200) ==")
fast = bench.rolling(50).mean(); slow = bench.rolling(200).mean()
w_series = (fast >= slow).astype(float)
weights = pd.DataFrame({bench_sym: w_series}, index=close.index)
metrics_of(weights, "Cross 50/200")

print("== OVERNIGHT DRIFT (close->next open) on NIFTYBEES ==")
op = pd.DataFrame({s: data[s]["Open"] for s in syms if s in data}).sort_index()
op = op.loc[:, close.columns]
ovr = (op.shift(-1) / close - 1).fillna(0)
P = (1 + ovr[bench_sym]).cumprod() * close[bench_sym].iloc[0]
P = P.to_frame(bench_sym)
# run engine on synthetic path so close-to-close return == overnight return
r = eng.run(pd.DataFrame({bench_sym: 1.0}, index=close.index), P, risk_mgr=risk, benchmark=bench)
m = r.metrics
print(f"{'Overnight NIFTYBEES':42s} ret={m['total_return']*100:7.1f}% cagr={m['cagr']*100:6.1f}% "
      f"sharpe={m['sharpe']:.2f} mdd={m['max_drawdown']*100:6.1f}% vol={m['volatility']*100:5.1f}%")

print("== OVERNIGHT DRIFT on equal-weight NIFTY50 basket ==")
ovr_b = (op.shift(-1) / close - 1).fillna(0)
port_ovr = ovr_b.mean(axis=1)
P2 = (1 + port_ovr).cumprod() * 1000
P2 = P2.to_frame("BASKET")
close_b = pd.DataFrame({"BASKET": P2["BASKET"]}, index=close.index)
r = eng.run(pd.DataFrame({"BASKET": 1.0}, index=close.index), close_b, risk_mgr=risk, benchmark=bench)
m = r.metrics
print(f"{'Overnight EW basket':42s} ret={m['total_return']*100:7.1f}% cagr={m['cagr']*100:6.1f}% "
      f"sharpe={m['sharpe']:.2f} mdd={m['max_drawdown']*100:6.1f}% vol={m['volatility']*100:5.1f}%")

print(f"\nBENCHMARK (buy&hold NIFTYBEES) = {(bench.iloc[-1]/bench.iloc[0]-1)*100:.1f}%")
