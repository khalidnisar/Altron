from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from altron.exceptions import LiveTradingDisabled


@dataclass(slots=True)
class Settings:
    """Runtime settings. Secrets are read from the environment, never persisted."""

    data_dir: Path = field(default_factory=lambda: Path(os.getenv("ALTRON_DATA_DIR", "data")))
    log_level: str = field(default_factory=lambda: os.getenv("ALTRON_LOG_LEVEL", "INFO"))
    paper_trading: bool = True
    max_position_fraction: float = 0.10
    max_portfolio_drawdown: float = 0.20
    telegram_bot_token: str | None = field(
        default_factory=lambda: os.getenv("TELEGRAM_BOT_TOKEN")
    )
    telegram_chat_id: str | None = field(
        default_factory=lambda: os.getenv("TELEGRAM_CHAT_ID")
    )
    discord_webhook_url: str | None = field(
        default_factory=lambda: os.getenv("DISCORD_WEBHOOK_URL")
    )

    def authorize_live_trading(self, explicit_flag: bool) -> None:
        """Require both a CLI flag and an environment acknowledgement.

        Broker implementations should call this immediately before every startup.
        """
        acknowledged = os.getenv("ALTRON_ENABLE_LIVE_TRADING") == "I_UNDERSTAND_THE_RISKS"
        if not explicit_flag or not acknowledged:
            raise LiveTradingDisabled(
                "Live trading is disabled. Paper mode is the default. To acknowledge risk, "
                "pass --live and set ALTRON_ENABLE_LIVE_TRADING=I_UNDERSTAND_THE_RISKS."
            )
        self.paper_trading = False

    def ensure_directories(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
