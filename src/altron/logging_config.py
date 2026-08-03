from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def configure_logging(
    level: str = "INFO",
    path: str | Path = "data/logs/altron.log",
    *,
    max_bytes: int = 10_000_000,
    backups: int = 5,
) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s", datefmt="%Y-%m-%dT%H:%M:%S%z"
    )
    file_handler = RotatingFileHandler(
        destination, maxBytes=max_bytes, backupCount=backups, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        handlers=[console, file_handler],
        force=True,
    )


def get_logger(name: str | None = None) -> logging.Logger:
    """Return a stdlib logger; equivalent to ``logging.getLogger(name)``."""
    return logging.getLogger(name if name is not None else "altron")
