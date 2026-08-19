"""Configuration loading: YAML file + environment overrides + defaults."""
from __future__ import annotations

import copy
import os
from pathlib import Path
from typing import Any

import yaml

from .models import SymbolSpec

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "config.yaml"


def _deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


class AppConfig:
    def __init__(self, data: dict[str, Any]):
        self.data = data
        self.symbols: dict[str, SymbolSpec] = {
            s["name"]: SymbolSpec(
                name=s["name"],
                base_price=float(s["base_price"]),
                digits=int(s["digits"]),
                point=float(s["point"]),
                pip=float(s["pip"]),
                spread_points=float(s["spread_points"]),
                slippage_points=float(s["slippage_points"]),
                contract_size=float(s["contract_size"]),
                tick_sigma=float(s["tick_sigma"]),
                quote_usd=float(s.get("quote_usd", 1.0)),
            )
            for s in data["symbols"]
        }

    # -- typed accessors -----------------------------------------------------
    def get(self, *path: str, default: Any = None) -> Any:
        node: Any = self.data
        for key in path:
            if not isinstance(node, dict) or key not in node:
                return default
            node = node[key]
        return node

    def f(self, *path: str, default: float = 0.0) -> float:
        return float(self.get(*path, default=default))

    def i(self, *path: str, default: int = 0) -> int:
        return int(self.get(*path, default=default))

    @property
    def port(self) -> int:
        return int(os.environ.get("TRADING_PORT", self.i("engine", "port", default=8100)))

    @property
    def broker_mode(self) -> str:
        return os.environ.get("TRADING_BROKER", str(self.get("engine", "broker", default="auto")))

    def public_dict(self) -> dict:
        """Config view safe for the dashboard (symbols reduced to specs)."""
        d = copy.deepcopy(self.data)
        d["symbols"] = [s["name"] for s in self.data["symbols"]]
        d["engine"]["broker"] = self.broker_mode
        return d


def load_config(path: str | os.PathLike | None = None) -> AppConfig:
    cfg_path = Path(path or os.environ.get("TRADING_CONFIG", DEFAULT_PATH))
    with open(cfg_path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return AppConfig(data)
