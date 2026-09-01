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
