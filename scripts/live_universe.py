"""List the live NSE F&O futures universe from Dhan's instrument master.

Run on the USER's machine (the scrip master is IP/region-blocked from the dev
sandbox). This proves the broader-universe path works and shows what the bot
would trade once `instruments: null` pulls from here.

    python scripts/live_universe.py [--indices-only]

Requires DHAN_CLIENT_ID in the environment (token fetched via the token service).
"""
from __future__ import annotations
import argparse
import sys

sys.path.insert(0, "src")

from quasar.config import load_config
from quasar.brokers import DhanBroker


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--indices-only", action="store_true")
    args = ap.parse_args()

    cfg = load_config()
    cid = cfg.get("broker.dhan.client_id") or __import__("os").environ.get("DHAN_CLIENT_ID")
    if not cid:
        print("ERROR: set DHAN_CLIENT_ID (or broker.dhan.client_id in config).")
        return 1
    b = DhanBroker(cid)
    try:
        uni = b.list_futures_universe(indices_only=args.indices_only)
    except Exception as e:  # pragma: no cover
        print(f"ERROR loading instrument master: {e}")
        print("The Dhan scrip master is reachable only from your machine, not the sandbox.")
        return 1

    idx = [u for u, m in uni.items() if m["is_index"]]
    stk = [u for u, m in uni.items() if not m["is_index"]]
    print(f"Live NSE F&O futures universe: {len(uni)} underlyings "
          f"({len(idx)} index, {len(stk)} stock)")
    print("\nIndex futures (what we'd trade first):")
    for u in sorted(idx):
        m = uni[u]
        print(f"  {u:<12} {m['trading_symbol']:<18} lot {m['lot_size']:<5} exp {m['expiry']}")
    if not args.indices_only:
        print(f"\nSample stock futures ({min(10, len(stk))} of {len(stk)}):")
        for u in sorted(stk)[:10]:
            m = uni[u]
            print(f"  {u:<12} {m['trading_symbol']:<18} lot {m['lot_size']:<5} exp {m['expiry']}")
    print("\nNext: set strategy.futures_ensemble.instruments: null and run the paper "
          "trader on this machine to trade the full universe.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
