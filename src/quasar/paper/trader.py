"""Paper trading loop for QUASAR.

Runs the live strategy on a trailing window, compares the target portfolio to the
current paper portfolio, simulates fills, and logs equity. A drawdown circuit
breaker halts new entries when portfolio drawdown breaches the configured limit.

Run daily (e.g. via cron at market close). In `paper` mode no real orders are
placed; set broker.mode to dhan/groww and supply credentials to route live.
"""
from __future__ import annotations
import json
import logging
import os
import time
from datetime import datetime
from typing import Dict, List

import numpy as np
import pandas as pd

from .. import indicators as ind
from ..config import load_config
from ..data.feed import build_feed
from ..strategies import build_strategy, required_symbols
from ..risk.manager import RiskManager

log = logging.getLogger("quasar.paper")


class PaperTrader:
    def __init__(self, cfg, state_file: str = "data/state.json", feed=None):
        self.cfg = cfg
        self.state_file = state_file
        self.feed = feed or build_feed(cfg)
        self.symbols = cfg.get("universe.symbols", [])
        self.regime_index = cfg.get("strategy.regime_filter.index", "NIFTYBEES.NS")
        self.initial = cfg.get("backtest.initial_capital", 1_000_000.0)
        self.risk = RiskManager(
            max_positions=cfg.get("risk.max_positions", 12),
            max_weight=cfg.get("risk.max_weight_per_position", 0.15),
            cash_buffer=cfg.get("risk.cash_buffer", 0.05),
            stop_loss_pct=cfg.get("risk.stop_loss_pct", 0.08),
            target_drawdown_pct=cfg.get("risk.target_drawdown_pct", 0.15),
        )
        self.history_days = 420
        self.state = self._load_state()

    def _load_state(self) -> dict:
        if os.path.exists(self.state_file):
            try:
                return json.load(open(self.state_file))
            except Exception:
                pass
        return {"cash": self.initial, "shares": {}, "equity_curve": [], "last_signal": {}}

    def _save_state(self):
        os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
        json.dump(self.state, open(self.state_file, "w"), indent=2, default=str)

    def _history(self) -> pd.DataFrame:
        strat = build_strategy(self.cfg)
        trade_symbol = getattr(strat, "trade_symbol", None)
        syms = required_symbols(self.cfg) + list(self.symbols)
        if trade_symbol:
            syms = [trade_symbol] + syms
        syms = list(dict.fromkeys(syms))
        end = datetime.now().strftime("%Y-%m-%d")
        start = (datetime.now() - pd.Timedelta(days=self.history_days)).strftime("%Y-%m-%d")
        data = self.feed.history(syms, start, end)
        close = pd.DataFrame({s: data[s]["Close"] for s in syms if s in data})
        vol = pd.DataFrame({s: data[s]["Volume"] for s in syms if s in data})
        close = close.dropna(how="all")
        vol = vol.reindex(close.index).fillna(0)
        return close, vol

    def compute_target(self) -> pd.Series:
        close, vol = self._history()
        strat = build_strategy(self.cfg)
        w = strat.run(close, vol)
        target = w.iloc[-1].copy()
        # apply risk limits to the single target row
        target = self.risk.apply(pd.DataFrame([target], index=[close.index[-1]])).iloc[0]
        return target

    def equity(self, prices: Dict[str, float]) -> float:
        eq = self.state["cash"]
        for s, sh in self.state["shares"].items():
            eq += sh * prices.get(s, 0.0)
        return eq

    def step(self) -> dict:
        target = self.compute_target()
        trade_syms = list(target.index)
        prices = self.feed.latest(trade_syms)
        if not prices:
            log.warning("No live prices; skipping step")
            return {}
        # current weights
        eq = self.equity(prices)
        cur_w = {s: (self.state["shares"].get(s, 0) * prices[s]) / eq for s in trade_syms if prices.get(s)}

        # circuit breaker
        if self.state["equity_curve"]:
            peak = max(r["equity"] for r in self.state["equity_curve"])
            dd = eq / peak - 1 if peak else 0
            if dd <= -self.risk.target_drawdown_pct:
                log.warning("CIRCUIT BREAKER: drawdown %.2f%% -> halting new entries", dd * 100)
                target = pd.Series(0.0, index=target.index)

        orders = []
        for s in self.symbols:
            tgt = target.get(s, 0.0)
            cur = cur_w.get(s, 0.0)
            delta = tgt - cur
            if abs(delta) < 1e-4:
                continue
            price = prices[s]
            value_delta = delta * eq
            qty = int(value_delta / price)
            if qty == 0:
                continue
            orders.append({"symbol": s, "qty": qty, "price": price, "side": "BUY" if qty > 0 else "SELL"})

        # apply fills
        for o in orders:
            s, qty, price = o["symbol"], o["qty"], o["price"]
            cost = qty * price
            self.state["cash"] -= cost
            self.state["shares"][s] = self.state["shares"].get(s, 0) + qty
            if self.state["shares"][s] == 0:
                self.state["shares"].pop(s, None)

        eq = self.equity(prices)
        self.state["equity_curve"].append({"date": datetime.now().isoformat(), "equity": eq})
        self.state["last_signal"] = {s: float(target.get(s, 0.0)) for s in self.symbols}
        self._save_state()

        log.info("STEP equity=%.2f orders=%d", eq, len(orders))
        return {"equity": eq, "orders": orders, "target": target.to_dict()}

    def run_once(self):
        return self.step()


def cfg_get(cfg, path, default):
    return cfg.get(path, default)


def main():
    import argparse
    ap = argparse.ArgumentParser(description="QUASAR paper trader")
    ap.add_argument("--once", action="store_true", help="run a single step and exit")
    ap.add_argument("--loop", action="store_true", help="run forever (poll hourly)")
    ap.add_argument("--poll", type=int, default=3600)
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    cfg = load_config()
    trader = PaperTrader(cfg)
    if args.once or not args.loop:
        res = trader.run_once()
        print("STEP result:", {k: (round(v, 2) if isinstance(v, float) else v)
                               for k, v in res.items() if k != "target"})
        if res.get("target") is not None:
            print("Signal (signed leverage):", {k: round(v, 3) for k, v in res["target"].items()})
    else:
        run_forever(args.poll)


def run_forever(poll_seconds: int = 3600):
    cfg = load_config()
    trader = PaperTrader(cfg)
    while True:
        try:
            trader.step()
        except Exception as e:  # pragma: no cover
            log.error("Step error: %s", e)
        time.sleep(poll_seconds)


if __name__ == "__main__":
    main()
