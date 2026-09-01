"""Index Trend Timing strategy with volatility targeting (QUASAR core, close-to-close).

Signal:
  - "above_ma"  : invest in the Nifty ETF when ^NSEI closes above its `ma_window` DMA.
  - "cross"     : invest when the `fast` DMA is above the `slow` DMA.
When the trend is down the strategy moves to cash (avoids crash drawdowns).

Overlay (vol targeting):
  The base strategy runs at ~9-10% realised volatility. To lift returns toward /
  past buy-and-hold while keeping risk controlled, we scale exposure by
  target_vol / realised_vol (20d), capped at `max_leverage`. This is the
  mechanism that harvests the persistent overnight drift embedded in the index
  cost-effectively (we only trade on exposure changes, not every session).
"""
from __future__ import annotations
import logging

import numpy as np
import pandas as pd

from .base import Strategy

log = logging.getLogger("quasar.strategy")


class IndexTrendStrategy(Strategy):
    name = "index_trend"

    def __init__(self, trade_symbol: str = "NIFTYBEES.NS", regime_index: str = "^NSEI",
                 mode: str = "above_ma", ma_window: int = 50, fast: int = 20,
                 slow: int = 50, vol_target: float = 0.15, max_leverage: float = 1.5,
                 vol_window: int = 20):
        self.trade_symbol = trade_symbol
        self.regime_index = regime_index
        self.mode = mode
        self.ma_window = ma_window
        self.fast = fast
        self.slow = slow
        self.vol_target = vol_target
        self.max_leverage = max_leverage
        self.vol_window = vol_window

    def run(self, close: pd.DataFrame, volume: pd.DataFrame) -> pd.DataFrame:
        dates = close.index
        px = close[self.regime_index] if self.regime_index in close.columns else close[self.trade_symbol]

        if self.mode == "above_ma":
            ma = px.rolling(self.ma_window).mean()
            signal = (px >= ma).astype(float)
        else:
            f = px.rolling(self.fast).mean()
            s = px.rolling(self.slow).mean()
            signal = (f >= s).astype(float)

        # realised volatility of the underlying (daily close-to-close)
        ret = px.pct_change().fillna(0.0)
        rv = ret.rolling(self.vol_window).std() * np.sqrt(252)
        lev = (self.vol_target / rv).clip(upper=self.max_leverage).fillna(0.0)
        # only apply leverage while invested; in cash, weight 0
        weight = (signal * lev).clip(upper=self.max_leverage)

        out = pd.DataFrame(0.0, index=dates, columns=[self.trade_symbol])
        out[self.trade_symbol] = weight
        return out
