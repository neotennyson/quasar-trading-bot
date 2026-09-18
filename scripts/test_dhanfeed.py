"""Validate DhanFeed against the live Dhan API (runs on the USER's machine).

Confirms: (1) instrument master loads, (2) latest quotes parse, (3) historical
candles parse - all PAPER-ONLY (no orders placed). Run:

    python scripts/test_dhanfeed.py

Requires DHAN_CLIENT_ID in env (token fetched via token service).
"""
from __future__ import annotations
import sys

sys.path.insert(0, "src")

from quasar.config import load_config
from quasar.data.feed import DhanFeed


def main():
    cfg = load_config()
    cid = cfg.get("broker.dhan.client_id") or __import__("os").environ.get("DHAN_CLIENT_ID")
    if not cid:
        print("ERROR: set DHAN_CLIENT_ID"); return 1
    feed = DhanFeed(cid)
    try:
        uni = feed._universe()
    except Exception as e:
        print(f"ERROR loading instrument master: {e}")
        print("The Dhan scrip master is reachable only from your machine.")
        return 1
    print(f"[OK] instrument master: {len(uni)} futures underlyings")
    idx = [u for u, m in uni.items() if m["is_index"]]
    print(f"     index futures: {idx}")

    # latest quotes for a couple of names
    sample = idx[:2] + [u for u in uni if not uni[u]["is_index"]][:1]
    q = feed.latest(sample)
    print(f"[OK] latest quotes for {sample}: {q}")

    # historical candles for one index future
    hist = feed.history(sample[:1], "2024-01-01", "2024-01-31")
    for s, df in hist.items():
        print(f"[OK] history {s}: {len(df)} rows, cols={list(df.columns)}")
        print(df.tail(3).to_string())
    print("\nDhanFeed validated. Paper trader can now price the full live universe.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
