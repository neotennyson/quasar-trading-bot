"""Futures trend strategy (QUASAR F&O mode).

Trades Nifty / Bank Nifty index FUTURES directionally:
  - LONG when the index is above its trend filter (e.g. 50-day MA),
  - SHORT when it is below,
  - FLAT (no position) is also allowed when vol targeting forces 0.

Exposure is sized by volatility targeting: leverage = target_vol / realised_vol,
capped at `max_leverage`. Because futures are leveraged instruments, this is the
mechanism that turns the persistent index drift/trend into amplified returns
while keeping single-trade risk bounded (the backtest engine also applies an
ATR-style stop and an account drawdown circuit breaker).

The strategy output is a single-column, SIGNED leverage series:
  weight in [-max_leverage, +max_leverage] on the chosen index column.
"""
from __future__ import annotations
import logging

import numpy as np
import pandas as pd

from .base import Strategy

log = logging.getLogger("quasar.strategy")


class FuturesTrendStrategy(Strategy):
    name = "futures_trend"

    def __init__(self, index: str = "^NSEI", mode: str = "above_ma",
                 ma_window: int = 50, fast: int = 20, slow: int = 50,
                 vol_target: float = 0.20, max_leverage: float = 3.0,
                 vol_window: int = 20, long_only: bool = False):
        self.index = index
        self.mode = mode
        self.ma_window = ma_window
        self.fast = fast
        self.slow = slow
        self.vol_target = vol_target
        self.max_leverage = max_leverage
        self.vol_window = vol_window
        self.long_only = long_only

    def run(self, close: pd.DataFrame, volume: pd.DataFrame) -> pd.DataFrame:
        dates = close.index
        px = close[self.index]

        if self.mode == "above_ma":
            ma = px.rolling(self.ma_window).mean()
            direction = np.where(px >= ma, 1.0, -1.0)
        else:
            f = px.rolling(self.fast).mean()
            s = px.rolling(self.slow).mean()
            direction = np.where(f >= s, 1.0, -1.0)
        direction = pd.Series(direction, index=dates)

        if self.long_only:
            direction = direction.clip(lower=0.0)

        ret = px.pct_change().fillna(0.0)
        rv = ret.rolling(self.vol_window).std() * np.sqrt(252)
        lev = (self.vol_target / rv).clip(upper=self.max_leverage).fillna(0.0)
        weight = (direction * lev).clip(-self.max_leverage, self.max_leverage)

        out = pd.DataFrame(0.0, index=dates, columns=[self.index])
        out[self.index] = weight
        return out
