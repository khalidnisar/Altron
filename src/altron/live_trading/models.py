from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class SignalEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timestamp: datetime
    symbol: str
    timeframe: str
    strategy: str
    signal: Literal[-1, 0, 1]
    params: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(ge=0, le=1)
    entry_price: float = Field(gt=0)
    source: str = "python"


class PaperFill(BaseModel):
    timestamp: datetime
    strategy: str
    symbol: str
    side: Literal["buy", "sell"]
    quantity: float = Field(gt=0)
    price: float = Field(gt=0)
    commission: float = Field(ge=0)
    realized_pnl: float = 0.0
