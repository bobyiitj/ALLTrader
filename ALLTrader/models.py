"""Pydantic data models — the lingua franca between layers."""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class AssetClass(str, Enum):
    STOCK = "stock"
    CRYPTO = "crypto"


class SignalType(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"
    NA = "N/A"


class Candle(BaseModel):
    """A single OHLCV bar."""
    model_config = ConfigDict(frozen=True)

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


class Quote(BaseModel):
    """Latest snapshot for an asset."""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    ticker: str
    asset_class: AssetClass
    price: float
    change_pct_24h: float | None = None
    volume_24h: float | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    is_stale: bool = False
    consecutive_failures: int = 0
    last_error: str | None = None


class Signal(BaseModel):
    """Indicator-derived trading signal."""
    ticker: str
    rsi: float | None
    signal: SignalType
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Alert(BaseModel):
    """User-defined price alert."""
    ticker: str
    target_price: float
    direction: Literal["above", "below", "either"] = "either"
    armed: bool = True
    last_fired: datetime | None = None
    last_price_seen: float | None = None  # for crossing detection


class ActivityEvent(BaseModel):
    """An entry in the user-visible activity log."""
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    ticker: str
    event: Literal["alert", "error", "info"]
    details: str
