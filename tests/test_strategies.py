"""Smoke tests for QUASAR strategies and backtest engine."""
from __future__ import annotations
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import numpy as np
import pandas as pd
import pytest

from quasar.config import load_config
from quasar.data.feed import YFinanceFeed
from quasar.strategies import build_strategy
from quasar.strategies.trend import IndexTrendStrategy
from quasar.risk.manager import RiskManager
from quasar.backtest.engine import BacktestEngine


@pytest.fixture(scope="module")
def market():
    cfg = load_config()
    feed = YFinanceFeed()
    syms = list(dict.fromkeys(["^NSEI", "NIFTYBEES.NS"] + cfg.get("universe.symbols")[:15]))
    data = feed.history(syms, "2020-01-01", "2023-12-31")
    close = pd.DataFrame({s: data[s]["Close"] for s in syms if s in data}).sort_index()
    close = close.loc[:, ~close.columns.duplicated()]
    vol = pd.DataFrame({s: data[s]["Volume"] for s in syms if s in data}).sort_index()
    vol = vol.reindex(close.index).fillna(0)
    return close, vol


def test_index_trend_weights_bounded(market):
    close, vol = market
    strat = IndexTrendStrategy(vol_target=0.15, max_leverage=1.5)
    w = strat.run(close, vol)
    assert (w >= 0).all().all()
    assert (w <= 1.5 + 1e-9).all().all()
    assert (w.sum(axis=1) > 0).any()


def test_backtest_runs_and_profits(market):
    close, vol = market
    cfg = load_config()
    strat = IndexTrendStrategy(vol_target=0.15, max_leverage=1.5)
    w = strat.run(close, vol)
    risk = RiskManager(max_positions=1, max_weight=1.5, cash_buffer=0.0,
                       stop_loss_pct=0.0, target_drawdown_pct=0.5)
    eng = BacktestEngine(initial_capital=cfg.get("backtest.initial_capital"))
    eng.cost_pct = 0.00175
    res = eng.run(w, close, risk_mgr=risk, benchmark=close["^NSEI"])
    assert res.metrics["final_equity"] > 0
    assert res.metrics["sharpe"] > 0.5


def test_risk_manager_caps_positions(market):
    close, vol = market
    strat = IndexTrendStrategy(vol_target=0.15, max_leverage=1.5)
    w = strat.run(close, vol)
    risk = RiskManager(max_positions=1, max_weight=0.15, cash_buffer=0.0,
                       stop_loss_pct=0.0, target_drawdown_pct=0.5)
    out = risk.apply(w)
    assert (out <= 0.15 + 1e-9).all().all()


def test_futures_strategy_signed_and_profitable(market):
    from quasar.strategies.futures import FuturesTrendStrategy
    from quasar.backtest.engine import BacktestEngine
    close, vol = market
    # restrict to index columns present in the fixture
    idx = "^NSEI" if "^NSEI" in close.columns else close.columns[0]
    sub = close[[idx]]
    strat = FuturesTrendStrategy(index=idx, vol_target=0.18, max_leverage=3.0, long_only=True)
    w = strat.run(sub, pd.DataFrame(index=sub.index, columns=sub.columns, data=0.0))
    # signed, bounded by leverage
    assert (w <= 3.0 + 1e-9).all().all()
    assert (w >= -3.0 - 1e-9).all().all()
    assert (w > 0).any().any()  # takes long positions sometimes
    eng = BacktestEngine(initial_capital=1_000_000.0)
    eng.cost_pct = 0.0002
    res = eng.run(w, sub, benchmark=sub[idx], futures=True, max_leverage=3.0,
                  account_dd=0.25, stop_pct=0.06)
    assert res.metrics["final_equity"] > 1_000_000.0
    assert res.metrics["sharpe"] > 0.5


def test_multi_trend_diversified(market):
    from quasar.strategies.futures import MultiTrendStrategy
    from quasar.backtest.engine import BacktestEngine
    close, vol = market
    insts = [c for c in close.columns if c.startswith(("^NSE", "RELIANCE", "TCS", "INFY", "ICICIBANK"))]
    if len(insts) < 2:
        insts = list(close.columns[:8])
    strat = MultiTrendStrategy(instruments=insts, portfolio_vol=0.15, gross_cap=3.0, long_only=True)
    w = strat.run(close, vol)
    assert w.shape[1] == len(insts)
    # gross leverage should be capped near gross_cap, not explosive
    assert w.abs().sum(axis=1).max() <= 3.0 + 1e-6
    eng = BacktestEngine(initial_capital=1_000_000.0)
    eng.cost_pct = 0.0002
    res = eng.run(w, close, benchmark=close["^NSEI"] if "^NSEI" in close.columns else close[close.columns[0]],
                  futures=True, max_leverage=2.0, account_dd=0.25, stop_pct=0.06)
    assert res.metrics["final_equity"] > 1_000_000.0
    assert res.metrics["max_drawdown"] > -0.6  # must not blow up
