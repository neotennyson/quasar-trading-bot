"""Broker adapters for QUASAR live trading (Dhan primary, Groww secondary).

Authentication uses the private token service via `quasar.brokers.tokens`
(TOKEN_API_KEY in .env). Order placement posts to the broker's REST API.

All network calls are stdlib-only (urllib) to avoid extra deps.

SAFETY: nothing here places an order unless `PaperTrader` is explicitly run with
live trading enabled (broker.live_trading: true). Default is paper — orders are
logged, never sent.
"""
from __future__ import annotations
import json
import logging
import os
import urllib.error
import urllib.request
import csv
import io
from typing import Optional

from . import tokens

log = logging.getLogger("quasar.broker")

UNDERLYING = {
    "^NSEI": "NIFTY",
    "^NSEBANK": "BANKNIFTY",
    "^NSEFIN": "FINNIFTY",
    "^NSEMID": "MIDCPNIFTY",
}


class OrderResult:
    def __init__(self, ok: bool, msg: str, order_id: Optional[str] = None):
        self.ok = ok
        self.msg = msg
        self.order_id = order_id


class BaseBroker:
    def __init__(self, name: str):
        self.name = name

    def validate(self) -> bool:
        raise NotImplementedError

    def resolve_future(self, symbol: str) -> Optional[dict]:
        raise NotImplementedError

    def place_order(self, symbol: str, qty: int, side: str, price: float | None = None) -> OrderResult:
        raise NotImplementedError


class DhanBroker(BaseBroker):
    BASE = "https://api.dhan.co/v2"
    SCRIPMASTER_URL = "https://api.dhan.co/v2/scripmaster"

    def __init__(self, client_id: str):
        super().__init__("dhan")
        self.client_id = client_id
        self._master: Optional[list] = None

    def _headers(self):
        return {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "access-token": tokens.get_token("dhan"),
            "client-id": self.client_id,
        }

    def validate(self) -> bool:
        try:
            req = urllib.request.Request(f"{self.BASE}/profile", method="GET", headers=self._headers())
            with urllib.request.urlopen(req, timeout=15) as r:
                return r.status == 200
        except Exception as e:  # pragma: no cover
            log.error("Dhan validate failed: %s", e)
            return False

    def _load_master(self):
        if self._master is not None:
            return self._master
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "cache", "dhan_scripmaster.csv")
        try:
            if os.path.exists(path):
                with open(path) as f:
                    self._master = list(csv.DictReader(f))
                return self._master
        except Exception:
            pass
        # download
        try:
            req = urllib.request.Request(self.SCRIPMASTER_URL, method="GET", headers=self._headers())
            with urllib.request.urlopen(req, timeout=30) as r:
                text = r.read().decode("utf-8")
            rows = list(csv.DictReader(io.StringIO(text)))
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w") as f:
                f.write(text)
            self._master = rows
            return rows
        except Exception as e:  # pragma: no cover
            log.error("Scripmaster download failed: %s", e)
            return []

    def resolve_future(self, symbol: str) -> Optional[dict]:
        underlying = UNDERLYING.get(symbol, symbol.replace(".NS", "").upper())
        master = self._load_master()
        cands = []
        for r in master:
            if r.get("SEM_EXM_TYP") != "FUT":
                continue
            if r.get("SEM_EXCH_CODE") != "NSE":
                continue
            tsym = r.get("SEM_TRADING_SYMBOL", "")
            if not tsym.startswith(underlying):
                continue
            cands.append(r)
        if not cands:
            return None
        # pick nearest expiry (SEM_EXPIRY_DATE YYYY-MM-DD)
        cands.sort(key=lambda r: r.get("SEM_EXPIRY_DATE", ""))
        best = cands[0]
        return {
            "trading_symbol": best["SEM_TRADING_SYMBOL"],
            "security_id": best["SEM_SMST_SEC_ID"],
            "lot_size": int(best.get("SEM_LOT_SIZE", 1) or 1),
            "expiry": best.get("SEM_EXPIRY_DATE", ""),
        }

    def place_order(self, symbol: str, qty: int, side: str, price: float | None = None) -> OrderResult:
        if qty <= 0:
            return OrderResult(False, "qty<=0")
        contract = self.resolve_future(symbol)
        if not contract:
            return OrderResult(False, f"no FUT contract for {symbol}")
        lots = max(1, round(qty / contract["lot_size"]))
        quantity = lots * contract["lot_size"]
        payload = {
            "dhanClientId": self.client_id,
            "transactionType": side,
            "exchangeSegment": "NSE_FO",
            "productType": "CARRY_FORWARD",
            "orderType": "MARKET",
            "validity": "DAY",
            "tradingSymbol": contract["trading_symbol"],
            "securityId": contract["security_id"],
            "quantity": quantity,
            "disclosedQuantity": 0,
            "price": 0,
            "triggerPrice": 0,
            "afterMarketOrder": False,
            "drvExpiryDate": contract["expiry"],
            "drvOptionType": "FUT",
            "drvStrikePrice": 0,
        }
        try:
            req = urllib.request.Request(f"{self.BASE}/orders", data=json.dumps(payload).encode(),
                                         method="POST", headers=self._headers())
            with urllib.request.urlopen(req, timeout=15) as r:
                body = json.loads(r.read().decode())
            oid = body.get("orderId") or body.get("data", {}).get("orderId")
            log.info("[DHAN] %s %d %s -> order %s", side, quantity, contract["trading_symbol"], oid)
            return OrderResult(True, "ok", oid)
        except urllib.error.HTTPError as e:
            return OrderResult(False, f"HTTP {e.code}: {e.read().decode()[:200]}")
        except Exception as e:  # pragma: no cover
            return OrderResult(False, str(e))


class GrowwBroker(BaseBroker):
    """Secondary broker. Uses the Groww access token; order signing mirrors
    Groww's documented v1 REST surface. Less battle-tested than Dhan here."""

    BASE = "https://api.groww.in/v1"

    def __init__(self, api_key: str):
        super().__init__("groww")
        self.api_key = api_key

    def validate(self) -> bool:
        try:
            req = urllib.request.Request(f"{self.BASE}/user/profile", method="GET",
                                         headers={"api-key": self.api_key, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=15) as r:
                return r.status == 200
        except Exception as e:  # pragma: no cover
            log.error("Groww validate failed: %s", e)
            return False

    def resolve_future(self, symbol: str) -> Optional[dict]:
        # Groww instrument mapping would be loaded from its instrument CSV;
        # left as a placeholder — use Dhan as the primary execution broker.
        log.warning("Groww resolve_future not implemented; use Dhan for F&O execution.")
        return None

    def place_order(self, symbol: str, qty: int, side: str, price: float | None = None) -> OrderResult:
        return OrderResult(False, "Groww order placement not implemented; use Dhan.")


def build_broker(cfg) -> Optional[BaseBroker]:
    mode = cfg.get("broker.mode", "paper")
    live = cfg.get("broker.live_trading", False)
    if mode == "paper" or not live:
        return None
    if mode == "dhan":
        cid = os.environ.get("DHAN_CLIENT_ID", cfg.get("broker.dhan.client_id", ""))
        if not cid:
            log.warning("Dhan client_id missing; cannot trade live.")
            return None
        return DhanBroker(cid)
    if mode == "groww":
        ak = os.environ.get("GROWW_API_KEY", cfg.get("broker.groww.api_key", ""))
        if not ak:
            log.warning("Groww api_key missing; cannot trade live.")
            return None
        return GrowwBroker(ak)
    return None
