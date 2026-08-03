"""YAML loading for monitor definitions."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from altron.monitor.models import Monitor


def _coerce_notify(value: Any) -> Any:
    """Accept either a NotifyConfig mapping or a list of channel names."""
    if isinstance(value, list):
        return {"channels": list(value)}
    return value


def load_monitor_file(path: str | Path) -> Monitor:
    """Load a single monitor from a YAML file."""
    payload = yaml.safe_load(Path(path).read_text())
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: top-level must be a mapping")
    if "monitor" in payload and isinstance(payload["monitor"], dict):
        payload = payload["monitor"]
    if "notify" in payload:
        payload["notify"] = _coerce_notify(payload["notify"])
    return Monitor.model_validate(payload)


def list_monitor_files(directory: str | Path) -> list[Path]:
    root = Path(directory)
    if not root.exists():
        return []
    files = list(root.glob("*.yaml")) + list(root.glob("*.yml"))
    return sorted({f.resolve() for f in files})


def load_monitors_from_directory(directory: str | Path) -> list[Monitor]:
    """Load every monitor YAML in ``directory``; skip files that fail to validate."""
    from altron.logging_config import get_logger

    logger = get_logger(__name__)
    monitors: list[Monitor] = []
    for path in list_monitor_files(directory):
        try:
            monitors.append(load_monitor_file(path))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Skipping %s: %s", path, exc)
    return monitors


def dump_monitor_yaml(monitor: Monitor) -> str:
    payload: dict[str, Any] = monitor.model_dump(mode="json")
    return yaml.safe_dump(payload, sort_keys=False, allow_unicode=True)
