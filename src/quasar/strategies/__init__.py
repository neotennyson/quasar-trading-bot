"""Factory: build the active QUASAR strategy from config."""
from __future__ import annotations
from typing import List

from ..config import Config
from .base import Strategy, MomentumStrategy, MeanReversionStrategy
from .ensemble import EnsembleStrategy
from .trend import IndexTrendStrategy
from .overnight import OvernightStrategy
from .futures import FuturesTrendStrategy, MultiTrendStrategy


def build_strategy(cfg: Config) -> Strategy:
    active = cfg.get("strategy.active", "index_trend")
    if active == "index_trend":
        p = cfg.get("strategy.index_trend", {})
        return IndexTrendStrategy(
            trade_symbol=p.get("trade_symbol", "NIFTYBEES.NS"),
            regime_index=p.get("regime_index", "^NSEI"),
            mode=p.get("mode", "above_ma"),
            ma_window=p.get("ma_window", 50),
            fast=p.get("fast", 20),
            slow=p.get("slow", 50),
            vol_target=p.get("vol_target", 0.15),
            max_leverage=p.get("max_leverage", 1.5),
            vol_window=p.get("vol_window", 20),
        )
    if active == "ensemble":
        sub = cfg.get("strategy.ensemble", {})
        return EnsembleStrategy(sub=sub, regime_index=cfg.get("strategy.regime_filter.index", "^NSEI"),
                                regime_ma=cfg.get("strategy.regime_filter.ma_window", 200))
    if active == "momentum":
        p = cfg.get("strategy.momentum", {})
        return MomentumStrategy(regime_index=p.get("regime_index", "^NSEI"),
                                regime_ma=p.get("regime_ma", 200), **{k: v for k, v in p.items()
                                if k not in ("regime_index", "regime_ma")})
    if active == "mean_reversion":
        p = cfg.get("strategy.mean_reversion", {})
        return MeanReversionStrategy(regime_index=p.get("regime_index", "^NSEI"),
                                     regime_ma=p.get("regime_ma", 200), **{k: v for k, v in p.items()
                                     if k not in ("regime_index", "regime_ma")})
    if active == "overnight":
        p = cfg.get("strategy.overnight", {})
        return OvernightStrategy(trade_symbol=p.get("trade_symbol", "NIFTYBEES.NS"),
                                 regime_index=p.get("regime_index", "^NSEI"),
                                 regime_ma=p.get("regime_ma", 200), mode=p.get("mode", "index"),
                                 top_n=p.get("top_n", 10), rebalance=p.get("rebalance", "W"))
    if active == "futures_trend":
        p = cfg.get("strategy.futures_trend", {})
        return FuturesTrendStrategy(
            index=p.get("index", "^NSEI"),
            mode=p.get("mode", "above_ma"),
            ma_window=p.get("ma_window", 50),
            fast=p.get("fast", 20),
            slow=p.get("slow", 50),
            vol_target=p.get("vol_target", 0.18),
            max_leverage=p.get("max_leverage", 3.0),
            vol_window=p.get("vol_window", 20),
            long_only=p.get("long_only", False),
        )
    if active == "multi_trend":
        p = cfg.get("strategy.multi_trend", {})
        insts = p.get("instruments") or required_symbols(cfg)
        return MultiTrendStrategy(
            instruments=insts,
            mode=p.get("mode", "above_ma"),
            ma_window=p.get("ma_window", 50),
            fast=p.get("fast", 20),
            slow=p.get("slow", 50),
            instr_vol=p.get("instr_vol", 0.10),
            portfolio_vol=p.get("portfolio_vol", 0.18),
            max_leverage=p.get("max_leverage", 3.0),
            gross_cap=p.get("gross_cap", 5.0),
            vol_window=p.get("vol_window", 20),
            long_only=p.get("long_only", True),
        )
    raise ValueError(f"Unknown strategy: {active}")


def required_symbols(cfg: Config) -> List[str]:
    """Symbols needed for the active strategy (indices + universe)."""
    syms = list(cfg.get("universe.symbols", []))
    syms = list(dict.fromkeys(syms + list(cfg.get("universe.indices", []))))
    rf = cfg.get("strategy.regime_filter.index", "^NSEI")
    if rf not in syms:
        syms = [rf] + syms
    # include the active strategy's own traded/index symbol
    try:
        strat = build_strategy(cfg)
        for attr in ("trade_symbol", "index", "instruments"):
            val = getattr(strat, attr, None)
            if isinstance(val, str) and val not in syms:
                syms = [val] + syms
    except Exception:
        pass
    return syms
