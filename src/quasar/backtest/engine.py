"""Backtest engine for QUASAR.

Simulates a daily-rebalanced long-only portfolio with:
  - transaction costs (commission + STT + slippage + impact)
  - per-position stop-loss
  - risk-manager constraints applied to target weights
  - benchmark comparison
"""
from __future__ import annotations
import logging
from dataclasses import dataclass, field
from typing import Dict, List

import numpy as np
import pandas as pd

from .. import indicators as ind

log = logging.getLogger("quasar.backtest")


@dataclass
class BacktestResult:
    equity: pd.Series
    trades: pd.DataFrame
    weights: pd.DataFrame
    metrics: Dict[str, float]
    benchmark_equity: pd.Series | None = None


class BacktestEngine:
    def __init__(self, initial_capital: float = 1_000_000.0,
                 commission_pct: float = 0.0005, stt_pct: float = 0.00025,
                 slippage_pct: float = 0.0005, impact_pct: float = 0.0005,
                 stop_loss_pct: float = 0.08):
        self.capital0 = initial_capital
        self.cost_pct = commission_pct + stt_pct + slippage_pct + impact_pct
        self.stop_loss_pct = stop_loss_pct

    def run(self, raw_weights: pd.DataFrame, close: pd.DataFrame,
            risk_mgr=None, benchmark: pd.Series | None = None,
            open_px: pd.DataFrame | None = None, overnight: bool = False,
            futures: bool = False, max_leverage: float = 3.0,
            account_dd: float = 0.25, stop_pct: float = 0.06) -> BacktestResult:
        symbols = list(raw_weights.columns)
        # risk manager may adjust target weights
        if futures:
            # signed leverage, bounded; shorts allowed
            w = raw_weights.clip(-max_leverage, max_leverage)
        elif risk_mgr is not None:
            w = risk_mgr.apply(raw_weights)
        else:
            w = raw_weights.clip(upper=1.0)

        equity = pd.Series(index=close.index, dtype=float)
        equity.iloc[0] = self.capital0
        w_prev = pd.Series(0.0, index=symbols)
        entry: Dict[str, float] = {}
        trades = []
        halted = False
        floor = self.capital0 * (1 - account_dd)
        recover = self.capital0 * (1 - account_dd * 0.5)

        if overnight:
            if open_px is None:
                raise ValueError("overnight mode requires open_px")
            end = len(close) - 1  # last day has no next open to exit
            for t in range(1, end):
                # overnight return: open[t] / close[t-1] - 1
                r = (open_px.iloc[t] / close.iloc[t - 1] - 1.0).fillna(0.0)
                port_ret = float((w_prev * r).sum())
                eq = equity.iloc[t - 1] * (1 + port_ret)
                w_target = w.iloc[t].copy()
                turnover = float((w_target - w_prev).abs().sum() / 2.0)
                cost = eq * turnover * self.cost_pct
                eq -= cost
                for s in symbols:
                    if w_target[s] > 0 and w_prev[s] == 0:
                        entry[s] = float(close[s].iloc[t])
                        trades.append((close.index[t], s, "ENTRY", w_target[s], close[s].iloc[t]))
                    if w_target[s] == 0 and s in entry:
                        entry.pop(s, None)
                equity.iloc[t] = eq
                w_prev = w_target
            equity.iloc[-1] = eq
        else:
            asset_ret = close.pct_change().fillna(0.0)
            for t in range(1, len(close)):
                r = asset_ret.iloc[t]
                port_ret = float((w_prev * r).sum())
                eq = equity.iloc[t - 1] * (1 + port_ret)

                w_target = w.iloc[t].copy()

                if futures:
                    # per-position stop (handles shorts), and account DD breaker
                    for s in symbols:
                        if w_prev[s] != 0 and s in entry:
                            adverse = (close[s].iloc[t] / entry[s] - 1.0)
                            if (w_prev[s] > 0 and adverse < -stop_pct) or \
                               (w_prev[s] < 0 and adverse > stop_pct):
                                w_target[s] = 0.0
                                trades.append((close.index[t], s, "STOP_EXIT",
                                               w_prev[s], close[s].iloc[t]))
                    if halted:
                        w_target = pd.Series(0.0, index=symbols)
                        if eq >= recover:
                            halted = False
                    elif eq < floor:
                        halted = True
                        w_target = pd.Series(0.0, index=symbols)
                else:
                    # stop-loss: exit positions that breached stop during the day
                    for s in symbols:
                        if w_prev[s] > 0 and s in entry:
                            if close[s].iloc[t] <= entry[s] * (1 - self.stop_loss_pct):
                                if w_target[s] > 0:
                                    trades.append((close.index[t], s, "STOP_EXIT",
                                                   w_prev[s], close[s].iloc[t]))
                                w_target[s] = 0.0

                turnover = float((w_target - w_prev).abs().sum() / 2.0)
                cost = eq * turnover * self.cost_pct
                eq -= cost

                for s in symbols:
                    if w_target[s] != 0 and w_prev[s] == 0:
                        entry[s] = float(close[s].iloc[t])
                        trades.append((close.index[t], s, "ENTRY",
                                       w_target[s], close[s].iloc[t]))
                    if w_target[s] == 0 and s in entry:
                        entry.pop(s, None)

                equity.iloc[t] = eq
                w_prev = w_target

        equity = equity.ffill()
        trades_df = pd.DataFrame(trades, columns=["date", "symbol", "action", "weight", "price"])

        bench = None
        if benchmark is not None:
            b = benchmark.reindex(close.index).ffill().bfill()
            bench = (b / b.iloc[0]) * self.capital0

        metrics = self._metrics(equity, bench)
        return BacktestResult(equity=equity, trades=trades_df, weights=w,
                              metrics=metrics, benchmark_equity=bench)

    @staticmethod
    def _metrics(equity: pd.Series, bench: pd.Series | None) -> Dict[str, float]:
        ret = equity.iloc[-1] / equity.iloc[0] - 1.0
        n_years = max((equity.index[-1] - equity.index[0]).days / 365.25, 1e-9)
        cagr = (equity.iloc[-1] / equity.iloc[0]) ** (1 / n_years) - 1.0
        daily = equity.pct_change().dropna()
        sharpe = float(daily.mean() / (daily.std() + 1e-12) * np.sqrt(252))
        mdd = ind.max_drawdown(equity)
        m = {
            "total_return": float(ret),
            "cagr": float(cagr),
            "sharpe": sharpe,
            "max_drawdown": mdd,
            "final_equity": float(equity.iloc[-1]),
            "volatility": float(daily.std() * np.sqrt(252)),
        }
        if bench is not None:
            ben_ret = bench.iloc[-1] / bench.iloc[0] - 1.0
            m["benchmark_return"] = float(ben_ret)
            m["excess_return"] = float(ret - ben_ret)
        return m
