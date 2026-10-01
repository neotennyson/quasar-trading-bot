"""Risk management layer for QUASAR.

Applies position-level and portfolio-level constraints to target weights, and
provides a drawdown circuit-breaker used by the live paper trader.

The strategy already performs its own internal risk sizing (per-instrument
leverage cap + gross exposure cap + volatility targeting). This layer is a
*pass-through safety overlay*: it keeps the strategy's two-way (long/short)
signals, clips to the same caps, and only scales down exposure on a gross
breach. It does NOT force a cash buffer or drop short legs, which would
silently convert a two-way trend book into a crippled long-only one.
"""
from __future__ import annotations
import logging

import numpy as np
import pandas as pd

log = logging.getLogger("quasar.risk")


class RiskManager:
    def __init__(self, max_positions: int = 15, max_weight: float = 2.0,
                 gross_cap: float = 3.0, cash_buffer: float = 0.0,
                 stop_loss_pct: float = 0.08, target_drawdown_pct: float = 0.25):
        self.max_positions = max_positions
        self.max_weight = max_weight
        self.gross_cap = gross_cap
        self.cash_buffer = cash_buffer
        self.stop_loss_pct = stop_loss_pct
        self.target_drawdown_pct = target_drawdown_pct

    def apply(self, target_weights: pd.DataFrame) -> pd.DataFrame:
        """Light safety overlay: keep two-way signals, clip to strategy caps."""
        rows = []
        for i in range(len(target_weights)):
            row = target_weights.iloc[i]
            # two-way: clip each leg to +/- max_weight (do NOT drop shorts)
            row = row.clip(lower=-self.max_weight, upper=self.max_weight)
            # cap the number of open positions (keep strongest convictions)
            if len(row) > self.max_positions:
                row = row.reindex(row.abs().sort_values(ascending=False).index).head(self.max_positions)
            # gross exposure cap (matches strategy.gross_cap)
            gross = row.abs().sum()
            cap = self.gross_cap * (1.0 - self.cash_buffer)
            if gross > cap and gross > 0:
                row = row * (cap / gross)
            full = pd.Series(0.0, index=target_weights.columns)
            full.update(row)
            rows.append(full)
        return pd.DataFrame(rows, index=target_weights.index)

    def breach_drawdown(self, equity: pd.Series) -> bool:
        if equity.empty:
            return False
        peak = equity.cummax().iloc[-1]
        dd = equity.iloc[-1] / peak - 1.0
        return dd <= -self.target_drawdown_pct
