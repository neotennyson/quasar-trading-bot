"""Configuration loading for QUASAR."""
from __future__ import annotations
import os
from dataclasses import dataclass, field
from typing import Any, Dict
import yaml


@dataclass
class Config:
    raw: Dict[str, Any]

    def get(self, path: str, default: Any = None) -> Any:
        cur = self.raw
        for part in path.split("."):
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            else:
                return default
        return cur


def _load_dotenv(path: str) -> None:
    """Populate os.environ from a .env file (setdefault; env beats file)."""
    try:
        text = open(path).read()
    except OSError:
        return
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _expand_env(obj):
    """Replace ${VAR} in string config values with environment variables."""
    if isinstance(obj, dict):
        return {k: _expand_env(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_expand_env(v) for v in obj]
    if isinstance(obj, str) and obj.startswith("${") and obj.endswith("}"):
        return os.environ.get(obj[2:-1], "")
    return obj


def load_config(path: str | None = None) -> Config:
    if path is None:
        path = os.environ.get("QUASAR_CONFIG",
                              os.path.join(os.path.dirname(__file__), "..", "..", "config.yaml"))
    # load .env beside the project root so ${VAR} placeholders resolve
    _load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))
    _load_dotenv(os.path.join(os.path.expanduser("~"), ".env"))
    with open(path, "r") as f:
        raw = yaml.safe_load(f)
    raw = _expand_env(raw)
    return Config(raw=raw)
