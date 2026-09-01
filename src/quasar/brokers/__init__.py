"""Broker adapter interfaces for QUASAR.

Paper mode never calls these. When broker.mode is dhan/groww and credentials are
present in config.yaml, the paper trader can route orders through these clients.

The HTTP plumbing is scaffolded; fill in endpoint paths / signing per the
broker's official API docs before live trading. All methods are no-ops until
explicitly enabled to avoid accidental live orders.
"""
from __future__ import annotations
import logging
from typing import List, Dict

log = logging.getLogger("quasar.broker")


class OrderResult:
    def __init__(self, ok: bool, msg: str, order_id: str | None = None):
        self.ok = ok
        self.msg = msg
        self.order_id = order_id


class BaseBroker:
    LIVE = False

    def place_order(self, symbol: str, qty: int, side: str, price: float) -> OrderResult:
        raise NotImplementedError

    def get_quote(self, symbol: str) -> float:
        raise NotImplementedError


class DhanBroker(BaseBroker):
    """Dhan API client. See https://api.dhan.co (developer docs)."""

    def __init__(self, client_id: str, access_token: str):
        self.client_id = client_id
        self.access_token = access_token

    def place_order(self, symbol, qty, side, price) -> OrderResult:
        if not self.access_token:
            return OrderResult(False, "Dhan not configured (no access_token)")
        # TODO: implement per Dhan order API (instrument master + order endpoint)
        log.info("[DHAN][DRY] %s %d %s @ %.2f", side, qty, symbol, price)
        return OrderResult(True, "dry-run", None)


class GrowwBroker(BaseBroker):
    """Groww API client. See https://groww.in (developer docs)."""

    def __init__(self, api_key: str, api_secret: str):
        self.api_key = api_key
        self.api_secret = api_secret

    def place_order(self, symbol, qty, side, price) -> OrderResult:
        if not self.api_key:
            return OrderResult(False, "Groww not configured (no api_key)")
        # TODO: implement per Groww order API
        log.info("[GROWW][DRY] %s %d %s @ %.2f", side, qty, symbol, price)
        return OrderResult(True, "dry-run", None)


def build_broker(cfg) -> BaseBroker | None:
    mode = cfg.get("broker.mode", "paper")
    if mode == "dhan":
        return DhanBroker(cfg.get("broker.dhan.client_id", ""),
                          cfg.get("broker.dhan.access_token", ""))
    if mode == "groww":
        return GrowwBroker(cfg.get("broker.groww.api_key", ""),
                           cfg.get("broker.groww.api_secret", ""))
    return None
