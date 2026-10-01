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


class MultiTrendStrategy(Strategy):
    """Multi-instrument trend portfolio (trade EVERYTHING the strategy works on).

    Runs the same trend + vol-target logic on every instrument in `instruments`
    (all indices and all stocks you supply), then combines them with **equal
    risk contribution** (risk parity): each name gets weight proportional to
    1/vol, so no single instrument dominates. The whole portfolio is scaled to
    a target volatility and capped at a gross-leverage limit. This is how a CTA
    harvests trends across the entire market instead of betting on one name.
    """
    name = "multi_trend"

    def __init__(self, instruments: list, mode: str = "above_ma", ma_window: int = 100,
                 fast: int = 20, slow: int = 50, instr_vol: float = 0.10,
                 portfolio_vol: float = 0.18, max_leverage: float = 3.0,
                 gross_cap: float = 5.0, vol_window: int = 20, long_only: bool = True,
                 trend_ma: int = 200, strength_band: float = 0.03, primary_gate: bool = False,
                 long_gate: bool = None, short_gate: bool = None):
        self.instruments = instruments
        self.mode = mode
        self.ma_window = ma_window
        self.fast = fast
        self.slow = slow
        self.instr_vol = instr_vol
        self.portfolio_vol = portfolio_vol
        self.max_leverage = max_leverage
        self.gross_cap = gross_cap
        self.vol_window = vol_window
        self.long_only = long_only
        self.trend_ma = trend_ma
        self.strength_band = strength_band
        self.primary_gate = primary_gate
        # Asymmetric confirmation: enter LONGs early (above fast MA) but only
        # SHORT on a confirmed downtrend (below both MAs). This captures bull
        # rallies fast while still protecting in real crashes (whipsaw-safe).
        self.long_gate = long_gate if long_gate is not None else primary_gate
        self.short_gate = short_gate if short_gate is not None else primary_gate

    def run(self, close: pd.DataFrame, volume: pd.DataFrame) -> pd.DataFrame:
        dates = close.index
        insts = [c for c in self.instruments if c in close.columns]
        raw = pd.DataFrame(0.0, index=dates, columns=insts)
        lo = 0.0 if self.long_only else -self.max_leverage
        # slow MA is used ONLY to measure trend strength (for leverage sizing),
        # NOT as a hard gate (a hard gate destroys bull-market capture).
        ma_slow = close.rolling(self.trend_ma).mean()

        for s in insts:
            px = close[s]
            ma = px.rolling(self.ma_window).mean()
            # long when price is above the fast MA (original rule). The optional
            # primary_gate also requires price > slow MA (stricter, fewer trades).
            above = px >= ma
            below_primary = px < ma_slow[s]
            if self.long_gate:
                # confirmed long: above BOTH fast and slow MA (stricter, fewer trades)
                long_sig = above & (px >= ma_slow[s])
            else:
                long_sig = above
            if self.short_gate:
                # confirmed short: below BOTH MAs (real downtrend; avoids whipsaw)
                short_sig = (~above) & below_primary
            else:
                short_sig = ~above
            if self.long_only:
                direction = long_sig.fillna(False).astype(float)
            else:
                direction = np.where(long_sig.fillna(False), 1.0,
                                     np.where(short_sig.fillna(False), -1.0, 0.0))

            ret = px.pct_change().fillna(0.0)
            rv = ret.rolling(self.vol_window).std() * np.sqrt(252)
            base_lev = (self.instr_vol / rv).clip(upper=self.max_leverage).fillna(0.0)
            # TREND STRENGTH: normalised gap between fast and slow MA (0..1),
            # using the ABSOLUTE gap so it works in BOTH directions. A weak
            # trend (fast ~ slow, gap ~ 0) -> tiny bet (kills whipsaw sizing);
            # a strong trend (up OR down) -> full size. This lets the bot short
            # real downtrends instead of just going flat.
            gap = (ma / ma_slow[s] - 1.0).abs().fillna(0.0)
            strength = (gap / self.strength_band).clip(0.0, 1.0)
        lev = base_lev * strength
        raw[s] = (direction * lev).clip(lo, self.max_leverage)

        # Covariance-aware vol targeting: scale the whole book so the ACTUAL
        # portfolio return volatility (which reflects real cross-asset
        # correlation, not an independence assumption) hits `portfolio_vol`.
        asset_ret = close[insts].pct_change().fillna(0.0)
        rp = (raw * asset_ret).sum(axis=1)          # portfolio return at raw weights
        rp_vol = rp.rolling(self.vol_window).std() * np.sqrt(252)
        scale = (self.portfolio_vol / rp_vol).fillna(0.0)
        w = raw.mul(scale, axis=0).clip(lo, self.max_leverage)

        # cap gross leverage (sum of |weights|) at gross_cap
        gross = w.abs().sum(axis=1)
        divisor = (gross / self.gross_cap).where(gross > self.gross_cap, 1.0)
        w = w.divide(divisor, axis=0)

        return w.fillna(0.0)


class FuturesEnsembleStrategy(Strategy):
    """Two-way futures ENSEMBLE: average of three uncorrelated alpha signals.

    Each signal produces a SIGNED leverage series (long/short/flat), volatility
    targeted so leverage = instr_vol / realised_vol (capped at max_leverage). The
    three sub-signals:

      1. TREND   - long above both MAs, short below both (no-man's-land flat),
                   sized by absolute trend strength (fast-vs-slow MA gap).
      2. BOLLINGER - long when price breaks above the upper band, short below
                     the lower band (mean-reversion-around-the-trend edge).
      3. BREAKOUT  - long on N-day high breakout, short on N-day low breakdown
                     (capture acceleration in either direction).

    Averaging decorrelates the alphas: trend carries the big sustained moves,
    Bollinger catches fades, breakout catches accelerations. The blend cuts
    drawdown and whipsaw bleed vs any single signal while staying profitable in
    BOTH up and down regimes (the whole point after the US-Iran shock).
    """
    name = "futures_ensemble"

    def __init__(self, instruments: list, ma_window: int = 75, trend_ma: int = 200,
                 strength_band: float = 0.03, primary_gate: bool = True,
                 boll_k: int = 20, boll_std: float = 2.0, breakout_n: int = 20,
                 instr_vol: float = 0.10, max_leverage: float = 2.0,
                 vol_window: int = 20, long_only: bool = False,
                 w_trend: float = 1.0, w_boll: float = 1.0, w_breakout: float = 1.0):
        self.instruments = instruments
        self.ma_window = ma_window
        self.trend_ma = trend_ma
        self.strength_band = strength_band
        self.primary_gate = primary_gate
        self.boll_k = boll_k
        self.boll_std = boll_std
        self.breakout_n = breakout_n
        self.instr_vol = instr_vol
        self.max_leverage = max_leverage
        self.vol_window = vol_window
        self.long_only = long_only
        self.w_trend = w_trend
        self.w_boll = w_boll
        self.w_breakout = w_breakout

    def _lev(self, px):
        ret = px.pct_change().fillna(0.0)
        rv = ret.rolling(self.vol_window).std() * np.sqrt(252)
        return (self.instr_vol / rv).clip(upper=self.max_leverage).fillna(0.0)

    def run(self, close: pd.DataFrame, volume: pd.DataFrame) -> pd.DataFrame:
        dates = close.index
        insts = [c for c in self.instruments if c in close.columns]
        out = pd.DataFrame(0.0, index=dates, columns=insts)
        ma_slow = close.rolling(self.trend_ma).mean()

        for s in insts:
            px = close[s]
            ma = px.rolling(self.ma_window).mean()
            lev = self._lev(px)
            lo = 0.0 if self.long_only else -self.max_leverage

            # 1. TREND
            above = px >= ma
            below_primary = px < ma_slow[s]
            if self.primary_gate:
                long_sig = above & (px >= ma_slow[s])
                short_sig = (~above) & below_primary
            else:
                long_sig = above
                short_sig = ~above
            trend_dir = np.where(long_sig.fillna(False), 1.0,
                                 np.where(short_sig.fillna(False), -1.0, 0.0))
            gap = (ma / ma_slow[s] - 1.0).abs().fillna(0.0)
            strength = (gap / self.strength_band).clip(0.0, 1.0)
            w_trend = pd.Series(trend_dir, index=dates) * lev * strength

            # 2. BOLLINGER (breakout of volatility bands, two-way)
            mid = px.rolling(self.boll_k).mean()
            sd = px.rolling(self.boll_k).std()
            up = mid + self.boll_std * sd
            dn = mid - self.boll_std * sd
            boll_dir = np.where(px > up, 1.0, np.where(px < dn, -1.0, 0.0))
            w_boll = pd.Series(boll_dir, index=dates) * lev

            # 3. BREAKOUT (N-day high/low channel)
            hi = px.rolling(self.breakout_n).max()
            lo_n = px.rolling(self.breakout_n).min()
            bo_dir = np.where(px > hi.shift(1), 1.0, np.where(px < lo_n.shift(1), -1.0, 0.0))
            w_break = pd.Series(bo_dir, index=dates) * lev

            w = (self.w_trend * w_trend + self.w_boll * w_boll + self.w_breakout * w_break)
            if (self.w_trend + self.w_boll + self.w_breakout) > 0:
                w = w / (self.w_trend + self.w_boll + self.w_breakout)
            out[s] = w.clip(lo, self.max_leverage)

        return out.fillna(0.0)
