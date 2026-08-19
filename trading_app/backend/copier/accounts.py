"""Follower account configuration + validation (max 10 followers)."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field, asdict

MODES = ("mirror", "proportional", "fixed_lot")
BROKER_TYPES = ("simulated", "mt5_demo")
MAX_FOLLOWERS = 10


@dataclass
class AccountCfg:
    label: str
    broker_type: str = "simulated"          # simulated | mt5_demo
    login: str = ""                          # MT5 login (display only; session is terminal-side)
    enabled: bool = True
    mode: str = "proportional"               # mirror | proportional | fixed_lot
    multiplier: float = 1.0                  # risk_setting, tetratensor parlance
    fixed_lots: float = 0.01                 # for fixed_lot mode
    max_lot: float = 10.0                    # hard per-trade cap on the follower
    symbols: list[str] | None = None         # None → copy all symbols
    reverse: bool = False                    # copy inverted (SL/TP swap roles)
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "AccountCfg":
        cfg = cls(
            label=str(data.get("label") or "Account"),
            broker_type=str(data.get("broker_type", "simulated")),
            login=str(data.get("login", "")),
            enabled=bool(data.get("enabled", True)),
            mode=str(data.get("mode", "proportional")),
            multiplier=float(data.get("multiplier", 1.0)),
            fixed_lots=float(data.get("fixed_lots", 0.01)),
            max_lot=float(data.get("max_lot", 10.0)),
            symbols=list(data["symbols"]) if data.get("symbols") else None,
            reverse=bool(data.get("reverse", False)),
            id=str(data.get("id") or uuid.uuid4().hex[:8]),
        )
        validate_cfg(cfg)
        return cfg


def validate_cfg(cfg: AccountCfg) -> None:
    if cfg.broker_type not in BROKER_TYPES:
        raise ValueError(f"broker_type must be one of {BROKER_TYPES}")
    if cfg.mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}")
    if not 0.01 <= cfg.multiplier <= 50:
        raise ValueError("multiplier must be within 0.01..50")
    if not 0.01 <= cfg.fixed_lots <= 100:
        raise ValueError("fixed_lots must be within 0.01..100")
    if not 0.01 <= cfg.max_lot <= 100:
        raise ValueError("max_lot must be within 0.01..100")
    if not (1 <= len(cfg.label) <= 40):
        raise ValueError("label must be 1..40 characters")
