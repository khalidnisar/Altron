from __future__ import annotations

from importlib import metadata
from typing import TypeVar

from altron.exceptions import StrategyError
from altron.strategies.base import Strategy

StrategyType = TypeVar("StrategyType", bound=type[Strategy])
_REGISTRY: dict[str, type[Strategy]] = {}
_ENTRY_POINTS_LOADED = False


def register_strategy(strategy_type: StrategyType) -> StrategyType:
    name = getattr(strategy_type, "name", "").strip().lower()
    if not name:
        raise StrategyError("A strategy plugin must define a non-empty class-level name")
    existing = _REGISTRY.get(name)
    if existing is not None and existing is not strategy_type:
        raise StrategyError(f"Strategy {name!r} is already registered")
    _REGISTRY[name] = strategy_type
    return strategy_type


def load_entry_points() -> None:
    global _ENTRY_POINTS_LOADED
    if _ENTRY_POINTS_LOADED:
        return
    for entry_point in metadata.entry_points(group="altron.strategies"):
        plugin = entry_point.load()
        register_strategy(plugin)
    _ENTRY_POINTS_LOADED = True


def get_strategy(name: str) -> Strategy:
    from altron.strategies import builtins  # noqa: F401

    load_entry_points()
    strategy_type = _REGISTRY.get(name.lower())
    if strategy_type is None:
        raise StrategyError(f"Unknown strategy {name!r}. Available: {', '.join(list_strategies())}")
    return strategy_type()


def list_strategies() -> list[str]:
    from altron.strategies import builtins  # noqa: F401

    load_entry_points()
    return sorted(_REGISTRY)
