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


def load_config(path: str | None = None) -> Config:
    if path is None:
        path = os.environ.get("QUASAR_CONFIG",
                              os.path.join(os.path.dirname(__file__), "..", "..", "config.yaml"))
    with open(path, "r") as f:
        raw = yaml.safe_load(f)
    return Config(raw=raw)
