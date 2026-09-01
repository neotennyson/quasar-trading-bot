"""Overnight Drift Capture strategy (QUASAR core).

The Indian market exhibits a persistent 'overnight drift': a large share of
equity returns accrue from close to next open, while the intraday session is
roughly flat-to-negative. QUASAR exploits this by holding positions ONLY
overnight (buy at close, sell at next open), gated by an index trend filter so
it steps aside during bear/overnight-gap-risk regimes.

Two modes:
  - "index"  : hold the Nifty ETF (NIFTYBEES) overnight when ^NSEI > 200-DMA.
  - "basket" : equal-weight the top-N momentum large-caps overnight, weekly
               rebalanced, also trend-gated. Higher return, higher turnover.
"""
from __future__ import annotations
import logging

import numpy as np
import pandas as pd

from .. import indicators as ind
from .base import Strategy

log = logging.getLogger("quasar.strategy")


class OvernightStrategy(Strategy):
    name = "overnight"

    def __init__(self, trade_symbol: str = "NIFTYBEES.NS",
                 regime_index: str = "^NSEI", regime_ma: int = 200,
                 mode: str = "index", top_n: int = 10,
                 rebalance: str = "W", lookback_days: int = 126,
                 skip_days: int = 21, cash_buffer: float = 0.0):
        self.trade_symbol = trade_symbol
        self.regime_index = regime_index
        self.regime_ma = regime_ma
        self.mode = mode
        self.top_n = top_n
        self.rebalance = rebalance
        self.lookback_days = lookback_days
        self.skip_days = skip_days
        self.cash_buffer = cash_buffer

    def run(self, close: pd.DataFrame, volume: pd.DataFrame) -> pd.DataFrame:
        dates = close.index
        if self.mode == "index":
            weights = pd.DataFrame(0.0, index=dates, columns=[self.trade_symbol])
            if self.regime_index in close.columns:
                ma = close[self.regime_index].rolling(self.regime_ma).mean()
                invested = (close[self.regime_index] >= ma).astype(float)
                weights[self.trade_symbol] = invested
            else:
                weights[self.trade_symbol] = 1.0
            return weights

        # basket mode: momentum selection, weekly rebalance, trend-gated
        cols = [c for c in close.columns if c != self.regime_index]
        weights = pd.DataFrame(0.0, index=dates, columns=cols)
        rb_dates = [g.index[-1] for _, g in close.groupby(close.index.to_period(self.rebalance))]
        regime_ok = (close[self.regime_index] >= close[self.regime_index].rolling(self.regime_ma).mean()) \
            if self.regime_index in close.columns else pd.Series(True, index=dates)

        mom_cache = {}
        for rd in rb_dates:
            pos = close.index.get_loc(rd)
            if pos < self.lookback_days + self.skip_days or not regime_ok.iloc[pos]:
                continue
            if rd not in mom_cache:
                window = close[cols].iloc[pos - (self.lookback_days + self.skip_days): pos + 1]
                past = window.iloc[0]
                recent = window.iloc[-self.skip_days - 1] if self.skip_days > 0 else window.iloc[-1]
                mom = (recent / past - 1.0)
                ranked = mom.dropna().sort_values(ascending=False)
                picks = ranked.head(self.top_n).index.tolist()
                mom_cache[rd] = picks
            for s in mom_cache[rd]:
                weights.loc[rd, s] = 1.0 / len(mom_cache[rd])
        weights = weights.ffill().fillna(0.0)
        return weights
