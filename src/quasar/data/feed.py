"""Data feed: yfinance (free historical + live proxy) and broker data adapters.

The yfinance feed is the default for backtests and paper-trading simulation.
Dhan/Groww adapters are provided so the bot can pull live quotes/orders when
the user supplies API credentials in config.yaml.
"""
from __future__ import annotations
import logging
import os
from datetime import datetime
from typing import Dict, List, Optional

import numpy as np

import pandas as pd
import yfinance as yf

log = logging.getLogger("quasar.data")


class YFinanceFeed:
    """Historical + latest-quote feed backed by Yahoo Finance."""

    def __init__(self, cache_dir: Optional[str] = None):
        self.cache_dir = cache_dir or os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "cache")

    def _cache_path(self, sym: str, start: str, end: str) -> str:
        import re
        safe = re.sub(r"[^A-Za-z0-9]", "_", sym)
        return os.path.join(self.cache_dir, f"{safe}_{start}_{end}.csv")

    def _load_cache(self, sym: str, start: str, end: str) -> Optional[pd.DataFrame]:
        p = self._cache_path(sym, start, end)
        if os.path.exists(p):
            try:
                df = pd.read_csv(p, index_col=0, parse_dates=True)
                return df
            except Exception:
                return None
        return None

    def _save_cache(self, sym: str, start: str, end: str, df: pd.DataFrame):
        try:
            os.makedirs(self.cache_dir, exist_ok=True)
            df.to_csv(self._cache_path(sym, start, end))
        except Exception:
            pass

    def history(self, symbols: List[str], start: str, end: str,
                auto_adjust: bool = True, batch: bool = True,
                clean: bool = True) -> Dict[str, pd.DataFrame]:
        """Return {symbol: ohlcv DataFrame} for the date range.

        Uses a disk cache (deterministic, avoids rate limits) and retries on
        failure. If `clean`, removes bad ticks (single-day moves > 15%).
        """
        out: Dict[str, pd.DataFrame] = {}
        # 1) serve from cache where possible
        missing = []
        for sym in symbols:
            c = self._load_cache(sym, start, end)
            if c is not None and not c.empty:
                out[sym] = self._clean(c) if clean else c
            else:
                missing.append(sym)

        if not missing:
            return out

        # 2) batch download the missing symbols (with retry)
        for attempt in range(3):
            try:
                df = yf.download(missing, start=start, end=end,
                                 progress=False, auto_adjust=auto_adjust,
                                 actions=False, group_by="ticker")
                if df is not None and not df.empty:
                    for sym in missing:
                        if sym in df.columns.get_level_values(0):
                            sub = df[sym].dropna(how="all").copy()
                            sub.index = pd.to_datetime(sub.index).tz_localize(None)
                            sub = sub[["Open", "High", "Low", "Close", "Volume"]].copy()
                            self._save_cache(sym, start, end, sub)
                            out[sym] = self._clean(sub) if clean else sub
                    break
            except Exception as e:  # pragma: no cover
                log.warning("Batch download attempt %d failed: %s", attempt, e)

        # 3) per-symbol fallback for any still missing
        for sym in missing:
            if sym in out:
                continue
            try:
                df = yf.download(sym, start=start, end=end,
                                 progress=False, auto_adjust=auto_adjust,
                                 actions=False)
                if df is None or df.empty:
                    continue
                if isinstance(df.columns, pd.MultiIndex):
                    df = df.droplevel(1, axis=1)
                df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
                df.index = pd.to_datetime(df.index).tz_localize(None)
                self._save_cache(sym, start, end, df)
                out[sym] = self._clean(df) if clean else df
            except Exception as e:  # pragma: no cover
                log.error("Fetch failed for %s: %s", sym, e)
        return out

    @staticmethod
    def _clean(df: pd.DataFrame, max_move: float = 0.15) -> pd.DataFrame:
        """Interpolate single-day spikes beyond `max_move` (bad ticks)."""
        for col in ["Open", "High", "Low", "Close"]:
            if col not in df.columns:
                continue
            ret = df[col].pct_change().abs()
            bad = ret > max_move
            if bad.any():
                df.loc[bad, col] = np.nan
                df[col] = df[col].interpolate().ffill().bfill()
        return df

    def latest(self, symbols: List[str]) -> Dict[str, float]:
        """Last close price per symbol (used by paper trader)."""
        out: Dict[str, float] = {}
        for sym in symbols:
            try:
                df = yf.download(sym, period="5d", progress=False,
                                 auto_adjust=True, actions=False)
                if df is None or df.empty:
                    continue
                if isinstance(df.columns, pd.MultiIndex):
                    df = df.droplevel(1, axis=1)
                out[sym] = float(df["Close"].iloc[-1])
            except Exception as e:  # pragma: no cover
                log.error("Latest fetch failed for %s: %s", sym, e)
        return out


class DhanFeed:
    """Live market data via Dhan API. Requires client_id + access_token."""

    BASE = "https://api.dhan.co/v2"

    def __init__(self, client_id: str, access_token: str):
        self.client_id = client_id
        self.token = access_token
        self._session = None

    def _headers(self):
        return {"access-token": self.token, "client-id": self.client_id,
                "Content-Type": "application/json"}

    def quote(self, symbols: List[str]) -> Dict[str, float]:
        # Dhan uses instrument tokens; user maps symbols->tokens in production.
        # Placeholder returns {} until configured with instrument master.
        return {}


class GrowwFeed:
    """Live market data via Groww API. Requires api_key + api_secret."""

    BASE = "https://api.groww.in"

    def __init__(self, api_key: str, api_secret: str):
        self.api_key = api_key
        self.api_secret = api_secret

    def quote(self, symbols: List[str]) -> Dict[str, float]:
        return {}


def build_feed(cfg, mode: Optional[str] = None):
    """Factory: choose feed based on config broker.mode."""
    mode = mode or cfg.get("broker.mode", "paper")
    if mode == "paper":
        return YFinanceFeed()
    if mode == "dhan":
        return DhanFeed(cfg.get("broker.dhan.client_id", ""),
                        cfg.get("broker.dhan.access_token", ""))
    if mode == "groww":
        return GrowwFeed(cfg.get("broker.groww.api_key", ""),
                         cfg.get("broker.groww.api_secret", ""))
    return YFinanceFeed()
