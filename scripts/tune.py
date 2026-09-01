#!/usr/bin/env python3
"""QUASAR strategy tuning sweep. Tries parameter combos, prints metrics."""
from __future__ import annotations
import logging, os, sys, itertools
import pandas as pd
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from quasar.config import load_config
from quasar.data.feed import YFinanceFeed
from quasar.strategies.base import MomentumStrategy, MeanReversionStrategy
from quasar.risk.manager import RiskManager
from quasar.backtest.engine import BacktestEngine

logging.disable(logging.CRITICAL)
cfg = load_config()
feed = YFinanceFeed()
syms = list(dict.fromkeys([cfg.get("strategy.regime_filter.index"), cfg.get("backtest.benchmark")] + cfg.get("universe.symbols")))
data = feed.history(syms, cfg.get("backtest.start"), cfg.get("backtest.end"))
close = pd.DataFrame({s: data[s]["Close"] for s in syms if s in data}).sort_index()
close = close.loc[:, ~close.columns.duplicated()]
vol = pd.DataFrame({s: data[s]["Volume"] for s in syms if s in data}).sort_index()
vol = vol.reindex(close.index).fillna(0)
bench = data[cfg.get("backtest.benchmark")]["Close"]

risk = RiskManager(max_positions=cfg.get("risk.max_positions"), max_weight=cfg.get("risk.max_weight_per_position"),
                   cash_buffer=cfg.get("risk.cash_buffer"), stop_loss_pct=cfg.get("risk.stop_loss_pct"),
                   target_drawdown_pct=cfg.get("risk.target_drawdown_pct"))
eng = BacktestEngine(initial_capital=cfg.get("backtest.initial_capital"),
                     commission_pct=cfg.get("costs.commission_pct"), stt_pct=cfg.get("costs.stt_pct"),
                     slippage_pct=cfg.get("costs.slippage_pct"), impact_pct=cfg.get("costs.impact_pct"),
                     stop_loss_pct=cfg.get("risk.stop_loss_pct"))

regime = cfg.get("strategy.regime_filter.index")
results = []
for lb, sk, tn, rf in itertools.product([63, 126, 189, 252], [10, 21], [8, 10, 12], [True, False]):
    m = MomentumStrategy(lookback_days=lb, skip_days=sk, top_n=tn, regime_index=regime if rf else None,
                         regime_ma=200, min_dollar_vol=5e6)
    w = m.run(close, vol)
    r = eng.run(w, close, risk_mgr=risk, benchmark=bench)
    results.append((f"MOM lb={lb} sk={sk} n={tn} rf={rf}", r.metrics))

df = pd.DataFrame({k: v for k, v in [(x[0], x[1]) for x in results]})
tbl = pd.DataFrame([{ "cfg": x[0], **{k: x[1][k] for k in ["total_return","cagr","sharpe","max_drawdown","volatility","excess_return"]}} for x in results])
pd.set_option("display.width", 200, "display.max_columns", 20)
print(tbl.sort_values("sharpe", ascending=False).to_string(index=False))
print("\nBENCHMARK total_return = %.2f%%" % ((bench.iloc[-1]/bench.iloc[0]-1)*100))
