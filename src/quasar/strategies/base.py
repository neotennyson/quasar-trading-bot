"""Strategy base + concrete strategies for QUASAR.

Every strategy exposes `run(close, volume) -> weights` where:
  close  : pd.DataFrame, index=dates, columns=symbols, values=close price
  volume : pd.DataFrame, same shape, values=share volume
  weights: pd.DataFrame, index=dates, columns=symbols, values=target weight
           (weights on non-rebalance dates are forward-filled by the engine)

Weights for a given rebalance date sum to <= 1.0 (the rest is cash).
"""
from __future__ import annotations
import logging
from typing import Dict, List

import numpy as np
import pandas as pd

from .. import indicators as ind

log = logging.getLogger("quasar.strategy")


class Strategy:
    name = "base"

    def run(self, close: pd.DataFrame, volume: pd.DataFrame) -> pd.DataFrame:
        raise NotImplementedError


class MomentumStrategy(Strategy):
    name = "momentum"

    def __init__(self, lookback_days: int = 126, skip_days: int = 21,
                 top_n: int = 10, min_dollar_vol: float = 5e6,
                 rebalance: str = "ME", regime_index: str | None = None,
                 regime_ma: int = 200):
        self.lookback_days = lookback_days
        self.skip_days = skip_days
        self.top_n = top_n
        self.min_dollar_vol = min_dollar_vol
        self.rebalance = rebalance
        self.regime_index = regime_index
        self.regime_ma = regime_ma

    def run(self, close: pd.DataFrame, volume: pd.DataFrame) -> pd.DataFrame:
        symbols = list(close.columns)
        dates = close.index
        # rebalance dates = last actual trading day in each month (no synthetic labels)
        rb_dates = [g.index[-1] for _, g in close.groupby(close.index.to_period("M"))]

        dollar_vol = (close * volume).rolling(20).mean()

        weights = pd.DataFrame(0.0, index=dates, columns=symbols)

        # regime filter series
        regime_ok = pd.Series(True, index=dates)
        if self.regime_index and self.regime_index in close.columns:
            idx_close = close[self.regime_index]
            ma = idx_close.rolling(self.regime_ma).mean()
            regime_ok = idx_close >= ma

        for rd in rb_dates:
            pos = close.index.get_loc(rd)
            if pos < self.lookback_days + self.skip_days:
                continue
            if not regime_ok.iloc[pos]:
                # stay in cash this period
                continue
            window = close.iloc[pos - (self.lookback_days + self.skip_days): pos + 1]
            # momentum from (lookback+skip) ago to `skip` ago
            past = window.iloc[0]
            recent = window.iloc[-self.skip_days - 1] if self.skip_days > 0 else window.iloc[-1]
            mom = recent / past - 1.0

            liq = dollar_vol.iloc[pos]
            mom = mom.where(liq >= self.min_dollar_vol, np.nan)

            ranked = mom.dropna().sort_values(ascending=False)
            picks = ranked.head(self.top_n).index.tolist()
            if not picks:
                continue

            # risk-parity style sizing: weight ~ 1/vol
            vols = {}
            for s in picks:
                r = close[s].iloc[pos - 60:pos + 1].pct_change().dropna()
                vols[s] = r.std() + 1e-9
            inv = pd.Series({s: 1.0 / vols[s] for s in picks})
            w = inv / inv.sum()
            # cap concentration
            w = w.clip(upper=0.15)
            w = w / w.sum()
            for s, wt in w.items():
                weights.loc[rd, s] = wt

        # forward-fill target weights between rebalances (0 = explicit exit, kept)
        weights = weights.ffill().fillna(0.0)
        return weights


class MeanReversionStrategy(Strategy):
    name = "mean_reversion"

    def __init__(self, rsi_period: int = 14, rsi_os: float = 32,
                 rsi_ob: float = 62, bb_period: int = 20, bb_std: float = 2.0,
                 hold_days: int = 10, max_positions: int = 8,
                 regime_index: str | None = None, regime_ma: int = 200):
        self.rsi_period = rsi_period
        self.rsi_os = rsi_os
        self.rsi_ob = rsi_ob
        self.bb_period = bb_period
        self.bb_std = bb_std
        self.hold_days = hold_days
        self.max_positions = max_positions
        self.regime_index = regime_index
        self.regime_ma = regime_ma

    def run(self, close: pd.DataFrame, volume: pd.DataFrame) -> pd.DataFrame:
        symbols = list(close.columns)
        dates = close.index
        weights = pd.DataFrame(0.0, index=dates, columns=symbols)

        # regime filter
        regime_ok = pd.Series(True, index=dates)
        if self.regime_index and self.regime_index in close.columns:
            idx_close = close[self.regime_index]
            ma = idx_close.rolling(self.regime_ma).mean()
            regime_ok = idx_close >= ma

        # precompute entry/exit signals per symbol
        long_until = {s: -1 for s in symbols}
        for i, d in enumerate(dates):
            if not regime_ok.iloc[i]:
                continue
            for s in symbols:
                px = close[s].iloc[:i + 1]
                if len(px) < max(self.bb_period, self.rsi_period) + 1:
                    continue
                r = ind.rsi(px, self.rsi_period).iloc[-1]
                lo, mid, hi = ind.bollinger(px, self.bb_period, self.bb_std)
                below = close[s].iloc[i] <= lo.iloc[-1]
                above = close[s].iloc[i] >= hi.iloc[-1]

                if long_until[s] >= i:
                    # currently holding: exit if RSI recovered or hit hold horizon
                    if r >= self.rsi_ob or (i - (long_until[s] - self.hold_days)) >= self.hold_days:
                        long_until[s] = -1
                elif r <= self.rsi_os and below:
                    long_until[s] = i + self.hold_days

        # convert holding windows to weights (equal weight among active longs)
        for i, d in enumerate(dates):
            active = [s for s in symbols if long_until[s] >= i]
            active = active[:self.max_positions]
            if active:
                w = 1.0 / len(active)
                for s in active:
                    weights.loc[d, s] = w

        weights = weights.ffill().fillna(0.0)
        return weights
