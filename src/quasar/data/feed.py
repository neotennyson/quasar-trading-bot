"""Data feed: yfinance (free historical + live proxy) and broker data adapters.

The yfinance feed is the default for backtests and paper-trading simulation.
Dhan/Groww adapters are provided so the bot can pull live quotes/orders when
the user supplies API credentials in config.yaml.
"""
from __future__ import annotations
import json
import logging
import os
import urllib.parse
import urllib.request
from datetime import datetime
from typing import Dict, List, Optional

import numpy as np

import pandas as pd
import yfinance as yf

from ..brokers import DhanBroker, tokens
from ..brokers import UNDERLYING

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
    """Live market data via Dhan REST API (quotes + daily candles).

    Used by the PAPER trader to price the LIVE futures universe (index + stock
    futures) with real quotes. It NEVER places orders - that is the broker's job,
    and the paper trader only routes to the broker when live_trading: true.

    Auth uses the token service (quasar.brokers.tokens) like the broker adapter.
    Symbol resolution (underlying -> securityId/expiry) reuses DhanBroker's
    instrument master, so it works for ANY NSE F&O future, not just the two
    yfinance provides.
    """

    BASE = "https://api.dhan.co/v2"
    QUOTE = f"{BASE}/quotes"
    CHART = f"{BASE}/charts"

    def __init__(self, client_id: str, access_token: str = ""):
        self.client_id = client_id
        self.token = access_token or tokens.get_token("dhan")
        self._broker = DhanBroker(client_id)
        self._uni = None  # cached live futures universe

    def _headers(self):
        return {"access-token": self.token, "client-id": self.client_id,
                "Content-Type": "application/json", "Accept": "application/json"}

    def _universe(self) -> dict:
        if self._uni is None:
            self._uni = self._broker.list_futures_universe()
        return self._uni

    def _resolve(self, sym: str) -> Optional[dict]:
        """Map a yfinance-style or plain underlying symbol to a live contract."""
        underlying = UNDERLYING.get(sym, sym.replace(".NS", "").upper())
        uni = self._universe()
        if underlying in uni:
            return uni[underlying]
        # try a startswith match (e.g. RELIANCE vs RELIANCE24SEP)
        for u, c in uni.items():
            if underlying.startswith(u):
                return c
        return None

    def _get(self, url: str, params: dict) -> Optional[dict]:
        try:
            req = urllib.request.Request(f"{url}?{urllib.parse.urlencode(params)}",
                                         headers=self._headers())
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:  # pragma: no cover
            log.error("DhanFeed GET %s failed: %s", url, e)
            return None

    def latest(self, symbols: List[str]) -> Dict[str, float]:
        """Last traded price per underlying symbol (paper trader fills at this)."""
        out: Dict[str, float] = {}
        for sym in symbols:
            c = self._resolve(sym)
            if not c:
                continue
            itype = "FUTIDX" if c["is_index"] else "FUTSTK"
            resp = self._get(self.QUOTE, {"securityId": c["security_id"],
                                          "exchangeSegment": "NSE_FO",
                                          "instrumentType": itype})
            if not resp:
                continue
            data = resp.get("data", resp)
            ltp = data.get("lastTradedPrice")
            if ltp is None:
                continue
            # Dhan quotes are in paise (integer); convert to rupees.
            price = float(ltp) / 100.0 if float(ltp) > 100000 else float(ltp)
            out[sym] = price
        return out

    def history(self, symbols: List[str], start: str, end: str,
                auto_adjust: bool = True, batch: bool = True,
                clean: bool = True) -> Dict[str, pd.DataFrame]:
        """Daily OHLCV candles per underlying from Dhan's chart API."""
        out: Dict[str, pd.DataFrame] = {}
        for sym in symbols:
            c = self._resolve(sym)
            if not c:
                log.warning("DhanFeed: no live contract for %s", sym)
                continue
            itype = "FUTIDX" if c["is_index"] else "FUTSTK"
            params = {"exchangeSegment": "NSE_FO", "instrumentType": itype,
                      "fromDate": start, "toDate": end}
            resp = self._get(f"{self.CHART}/{c['security_id']}", params)
            df = self._parse_chart(resp)
            if df is not None and not df.empty:
                out[sym] = self._clean(df) if clean else df
        return out

    @staticmethod
    def _parse_chart(resp: Optional[dict]) -> Optional[pd.DataFrame]:
        """Defensive parse of Dhan's chart payload (format varies by endpoint)."""
        if not resp:
            return None
        data = resp.get("data", resp)
        if isinstance(data, dict):
            data = data.get("data", data)
        if not isinstance(data, list) or not data:
            log.warning("DhanFeed: unexpected chart shape: %s", str(resp)[:200])
            return None
        rows = []
        for row in data:
            if isinstance(row, (list, tuple)):
                if len(row) >= 6:       # [ts, o, h, l, c, v]
                    rows.append((row[0], row[1], row[2], row[3], row[4], row[5]))
                elif len(row) == 5:     # [o, h, l, c, v] (synthetic index)
                    rows.append((len(rows), row[0], row[1], row[2], row[3], row[4]))
            elif isinstance(row, dict):
                rows.append((row.get("timestamp", len(rows)),
                             row.get("open"), row.get("high"), row.get("low"),
                             row.get("close"), row.get("volume")))
        if not rows:
            return None
        df = pd.DataFrame(rows, columns=["ts", "Open", "High", "Low", "Close", "Volume"])
        df["ts"] = pd.to_numeric(df["ts"], errors="coerce")
        # epoch ms if huge, else assume ascending trading-day count
        if df["ts"].dropna().gt(1e11).any():
            df.index = pd.to_datetime(df["ts"], unit="ms")
        else:
            df.index = pd.date_range(end=pd.Timestamp.now().normalize(),
                                     periods=len(df), freq="B")[::-1][::-1]
        df = df[["Open", "High", "Low", "Close", "Volume"]].apply(
            pd.to_numeric, errors="coerce").ffill().bfill()
        return df

    @staticmethod
    def _clean(df: pd.DataFrame, max_move: float = 0.15) -> pd.DataFrame:
        for col in ["Open", "High", "Low", "Close"]:
            if col not in df.columns:
                continue
            ret = df[col].pct_change().abs()
            bad = ret > max_move
            if bad.any():
                df.loc[bad, col] = np.nan
                df[col] = df[col].interpolate().ffill().bfill()
        return df


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
