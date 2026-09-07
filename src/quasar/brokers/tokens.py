"""Broker token client for QUASAR.

Fetches fresh Dhan/Groww access tokens from the private token service
(tokens.example.invalid) using TOKEN_API_KEY, caching in
~/.broker_tokens.json. Mirrors the proven Nemesis logic but without the
execution fence (QUASAR is an execution bot and is authorised to trade).

Stdlib only. Safe: never prints token values.
"""
from __future__ import annotations
import datetime as dt
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE_URL = "https://tokens.example.invalid"
CACHE_PATH = Path.home() / ".broker_tokens.json"
BROKERS = ("dhan", "groww")
EXPIRY_MARGIN_SECONDS = 30 * 60
REQUEST_TIMEOUT = 15
ENV_PATHS = [
    Path.home() / ".env",
    Path(__file__).resolve().parent.parent.parent.parent / ".env",  # repo root
    Path("/Users/USER/Documents/Nemesis/.env"),
]


class TokenError(RuntimeError):
    pass


class TokenAPIUnreachable(TokenError):
    pass


class TokenIssuerStale(TokenError):
    pass


def _load_dotenv_if_needed() -> None:
    if os.environ.get("TOKEN_API_KEY", "").strip():
        return
    for p in ENV_PATHS:
        try:
            text = p.read_text()
        except OSError:
            continue
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _api_key() -> str:
    _load_dotenv_if_needed()
    key = os.environ.get("TOKEN_API_KEY", "").strip()
    if not key:
        raise TokenError("TOKEN_API_KEY not set (checked env + .env files).")
    return key


def _parse_expiry(raw) -> float | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    text = raw.strip().replace("Z", "+00:00")
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%d/%m/%Y %H:%M", "%Y-%m-%d"):
            try:
                parsed = dt.datetime.strptime(text, fmt)
                break
            except ValueError:
                continue
        else:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone(dt.timedelta(hours=5, minutes=30)))
    return parsed.timestamp()


def _read_cache() -> dict:
    try:
        with CACHE_PATH.open() as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _write_cache(cache: dict) -> None:
    tmp = CACHE_PATH.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w") as fh:
            json.dump(cache, fh, indent=2)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
    os.replace(tmp, CACHE_PATH)
    os.chmod(CACHE_PATH, 0o600)


def _is_fresh(entry) -> bool:
    if not isinstance(entry, dict) or not entry.get("token"):
        return False
    exp = _parse_expiry(entry.get("expiry"))
    if exp is None:
        return False
    return (exp - time.time()) > EXPIRY_MARGIN_SECONDS


def _fetch(broker: str) -> dict:
    url = f"{BASE_URL}/token/{broker}"
    req = urllib.request.Request(url, headers={"X-API-Key": _api_key(), "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            payload = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise TokenAPIUnreachable(f"Token API rejected key (HTTP {e.code}). Check TOKEN_API_KEY.")
        raise TokenAPIUnreachable(f"Token API HTTP {e.code} for {url}.")
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise TokenAPIUnreachable(f"Cannot reach token API at {BASE_URL}: {e}")
    except json.JSONDecodeError as e:
        raise TokenAPIUnreachable(f"Token API non-JSON response: {e}")
    token = payload.get("token") if isinstance(payload, dict) else None
    if not isinstance(token, str) or not token:
        raise TokenAPIUnreachable(f"Token API returned no 'token' for {broker}.")
    return {"token": token, "expiry": payload.get("expiry"),
            "updated": payload.get("updated"),
            "fetched_at": dt.datetime.now(dt.timezone.utc).isoformat()}


def get_token(broker: str, *, force: bool = False) -> str:
    """Return a fresh access token for `broker` ('dhan' / 'groww')."""
    broker = broker.strip().lower()
    if broker not in BROKERS:
        raise ValueError(f"unknown broker {broker!r}")
    cache = _read_cache()
    entry = cache.get(broker)
    if not force and _is_fresh(entry):
        return entry["token"]
    fresh = _fetch(broker)
    if not _is_fresh(fresh):
        raise TokenIssuerStale(
            f"Token issuer served an ALREADY-EXPIRED {broker} token "
            f"(expiry={fresh.get('expiry')}). POST {BASE_URL}/refresh, wait, refetch.")
    cache[broker] = fresh
    try:
        _write_cache(cache)
    except OSError:
        pass
    return fresh["token"]


def token_status(broker: str) -> dict:
    entry = _read_cache().get(broker.strip().lower())
    if not isinstance(entry, dict) or not entry.get("token"):
        return {"broker": broker, "cached": False, "fresh": False, "expiry": None}
    exp = _parse_expiry(entry.get("expiry"))
    return {"broker": broker, "cached": True, "fresh": _is_fresh(entry),
            "expiry": entry.get("expiry"),
            "seconds_remaining": int(exp - time.time()) if exp else None}
