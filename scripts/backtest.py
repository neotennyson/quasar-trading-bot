#!/usr/bin/env python3
"""QUASAR backtest runner.

Fetches historical data for the active strategy, runs it through the backtest
engine with realistic costs + risk controls, and reports performance vs the
Nifty benchmark. Saves equity-curve and trade CSVs.

Usage:
  python scripts/backtest.py [--start YYYY-MM-DD] [--end YYYY-MM-DD] [--save]
"""
from __future__ import annotations
import argparse
import logging
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from quasar.config import load_config
from quasar.data.feed import YFinanceFeed
from quasar.strategies import build_strategy
from quasar.risk.manager import RiskManager
from quasar.backtest.engine import BacktestEngine

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("quasar.backtest_cli")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start")
    ap.add_argument("--end")
    ap.add_argument("--save", action="store_true")
    args = ap.parse_args()

    cfg = load_config()
    start = args.start or cfg.get("backtest.start", "2016-01-01")
    end = args.end or cfg.get("backtest.end", "2024-12-31")

    strat = build_strategy(cfg)
    active = cfg.get("strategy.active", "index_trend")
    regime_index = cfg.get("strategy.regime_filter.index", "^NSEI")
    trade_symbol = getattr(strat, "trade_symbol", None)
    fut_index = getattr(strat, "index", None)
    universe = list(cfg.get("universe.symbols", []))

    is_futures = (active in ("futures_trend", "multi_trend"))
    bench_sym = "^NSEI" if is_futures else cfg.get("backtest.benchmark", "^NSEI")

    # include the instruments the active strategy actually trades (e.g. the 4 index
    # futures) so they are fetched even when they aren't in universe.symbols.
    strat_syms = []
    for _a in ("instruments", "index", "trade_symbol"):
        _v = getattr(strat, _a, None)
        if isinstance(_v, list):
            strat_syms += _v
        elif isinstance(_v, str):
            strat_syms.append(_v)

    needed = list(dict.fromkeys([regime_index, bench_sym] + strat_syms
                                 + ([trade_symbol] if trade_symbol else [])
                                 + ([fut_index] if fut_index else []) + universe))
    log.info("Downloading history %s..%s for %d symbols (strategy=%s)", start, end, len(needed), active)
    feed = YFinanceFeed()
    data = feed.history(needed, start, end)
    missing = [s for s in needed if s not in data]
    if missing:
        log.warning("Missing data for: %s", missing)

    avail = [s for s in needed if s in data]
    close = pd.DataFrame({s: data[s]["Close"] for s in avail}).sort_index()
    close = close.loc[:, ~close.columns.duplicated()]
    volume = pd.DataFrame({s: data[s]["Volume"] for s in avail}).sort_index()
    volume = volume.reindex(close.index).fillna(0)

    log.info("Running strategy: %s", active)
    target = strat.run(close, volume)

    risk = RiskManager(
        max_positions=cfg.get("risk.max_positions", 12),
        max_weight=cfg.get("risk.max_weight_per_position", 0.15),
        cash_buffer=cfg.get("risk.cash_buffer", 0.05),
        stop_loss_pct=cfg.get("risk.stop_loss_pct", 0.08),
        target_drawdown_pct=cfg.get("risk.target_drawdown_pct", 0.15),
    )
    bench_close = close[bench_sym] if bench_sym in close.columns else None
    engine = BacktestEngine(
        initial_capital=cfg.get("backtest.initial_capital", 1_000_000.0),
        commission_pct=cfg.get("costs.commission_pct", 0.0005),
        stt_pct=cfg.get("costs.stt_pct", 0.00025),
        slippage_pct=cfg.get("costs.slippage_pct", 0.0005),
        impact_pct=cfg.get("costs.impact_pct", 0.0005),
        stop_loss_pct=cfg.get("risk.stop_loss_pct", 0.08),
    )
    if is_futures:
        cf = cfg.get("costs_futures", {})
        engine.cost_pct = cf.get("cost_pct", 0.0002)
        result = engine.run(target, close, benchmark=bench_close, futures=True,
                            max_leverage=cf.get("max_leverage", 3.0),
                            account_dd=cf.get("account_dd", 0.25),
                            stop_pct=cf.get("stop_pct", 0.06))
    else:
        result = engine.run(target, close, risk_mgr=risk, benchmark=bench_close)

    m = result.metrics
    print("\n" + "=" * 64)
    print("QUASAR BACKTEST RESULT  (strategy: %s)" % active)
    print("=" * 64)
    print(f"Period            : {close.index[0].date()} -> {close.index[-1].date()}")
    print(f"Total return      : {m['total_return']*100:8.2f}%")
    if "benchmark_return" in m:
        print(f"Benchmark return  : {m['benchmark_return']*100:8.2f}%  ({bench_sym})")
        print(f"Excess return     : {m['excess_return']*100:8.2f}%")
    print(f"CAGR              : {m['cagr']*100:8.2f}%")
    print(f"Sharpe            : {m['sharpe']:8.2f}")
    print(f"Max drawdown      : {m['max_drawdown']*100:8.2f}%")
    print(f"Volatility        : {m['volatility']*100:8.2f}%")
    print(f"Final equity      : Rs {m['final_equity']:,.0f}")
    print("=" * 64)
    print(f"Total trades      : {len(result.trades)}")
    if not result.trades.empty:
        print(result.trades["action"].value_counts().to_dict())

    if args.save:
        os.makedirs("data", exist_ok=True)
        result.equity.to_csv("data/equity_curve.csv", header=["equity"])
        result.trades.to_csv("data/trades.csv", index=False)
        log.info("Saved equity_curve.csv and trades.csv")

    return result


if __name__ == "__main__":
    main()
