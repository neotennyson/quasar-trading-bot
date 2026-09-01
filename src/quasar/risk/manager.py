"""Risk management layer for QUASAR.

Applies position-level and portfolio-level constraints to target weights, and
provides a drawdown circuit-breaker used by the live paper trader.
"""
from __future__ import annotations
import logging

import numpy as np
import pandas as pd

log = logging.getLogger("quasar.risk")


class RiskManager:
    def __init__(self, max_positions: int = 12, max_weight: float = 0.15,
                 cash_buffer: float = 0.05, stop_loss_pct: float = 0.08,
                 target_drawdown_pct: float = 0.15):
        self.max_positions = max_positions
        self.max_weight = max_weight
        self.cash_buffer = cash_buffer
        self.stop_loss_pct = stop_loss_pct
        self.target_drawdown_pct = target_drawdown_pct

    def apply(self, target_weights: pd.DataFrame) -> pd.DataFrame:
        """Enforce max positions, per-position cap, and cash buffer."""
        rows = []
        for i in range(len(target_weights)):
            row = target_weights.iloc[i]
            row = row[row > 0].clip(upper=self.max_weight)
            if len(row) > self.max_positions:
                row = row.sort_values(ascending=False).head(self.max_positions)
            investable = 1.0 - self.cash_buffer
            if row.sum() > investable:
                row = row * (investable / row.sum())
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
