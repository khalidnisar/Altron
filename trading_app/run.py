"""Entry point:  python -m trading_app.run   (or: python trading_app/run.py)"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from trading_app.backend.config import load_config  # noqa: E402


def main() -> None:
    import uvicorn

    cfg = load_config(os.environ.get("TRADING_CONFIG"))
    uvicorn.run("trading_app.backend.app:create_app", factory=True,
                host="0.0.0.0", port=cfg.port, log_level="info")


if __name__ == "__main__":
    main()
