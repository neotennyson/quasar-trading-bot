"""Ensemble strategy: blends momentum + mean-reversion target weights."""
from __future__ import annotations
import logging

import numpy as np
import pandas as pd

from .base import Strategy, MomentumStrategy, MeanReversionStrategy

log = logging.getLogger("quasar.strategy")


class EnsembleStrategy(Strategy):
    name = "ensemble"

    def __init__(self, sub: dict, regime_index: str | None = None, regime_ma: int = 200):
        self.w_mom = sub.get("momentum", 0.65)
        self.w_mr = sub.get("mean_reversion", 0.35)
        self.regime_index = regime_index
        self.regime_ma = regime_ma
        self.momentum = MomentumStrategy(regime_index=regime_index, regime_ma=regime_ma, **sub.get("_mom_kwargs", {}))
        self.meanrev = MeanReversionStrategy(regime_index=regime_index, regime_ma=regime_ma, **sub.get("_mr_kwargs", {}))

    def run(self, close: pd.DataFrame, volume: pd.DataFrame) -> pd.DataFrame:
        wm = self.momentum.run(close, volume)
        wr = self.meanrev.run(close, volume)
        blended = self.w_mom * wm + self.w_mr * wr
        # renormalize to <=1 (cash remainder allowed)
        row_sum = blended.sum(axis=1)
        scaled = blended.div(row_sum.where(row_sum > 1.0, 1.0), axis=0)
        return scaled.clip(upper=1.0).fillna(0.0)
