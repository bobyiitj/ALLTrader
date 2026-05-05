"""Application configuration loaded from environment variables.

All settings live here — no magic constants scattered across the codebase.
Misconfiguration fails loudly at startup via Pydantic validation.
"""
from __future__ import annotations

from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Strongly-typed application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Refresh / scheduling ---
    refresh_interval_sec: int = Field(default=10, ge=5, le=300)
    fetch_timeout_sec: float = Field(default=8.0, gt=0, le=60)
    max_backoff_sec: float = Field(default=30.0, gt=0)
    stale_threshold_failures: int = Field(default=3, ge=1)

    # --- RSI parameters ---
    rsi_period: int = Field(default=14, ge=2, le=100)
    rsi_oversold: float = Field(default=30.0, ge=0, le=100)
    rsi_overbought: float = Field(default=70.0, ge=0, le=100)

    # --- Crypto provider ---
    crypto_exchange: str = Field(default="binance")
    crypto_fallback: str = Field(default="kraken")

    # --- Alerts ---
    alert_cooldown_sec: int = Field(default=300, ge=0)

    # --- Logging / chart ---
    log_level: str = Field(default="INFO")
    chart_history_points: int = Field(default=500, ge=10, le=10000)

    # --- Default watchlists (overridable in UI) ---
    default_stocks: tuple[str, ...] = ("AAPL", "NVDA", "MSFT")
    default_cryptos: tuple[str, ...] = ("BTC/USDT", "ETH/USDT", "SOL/USDT")

    # --- Persistence ---
    state_dir: Path = Field(default=Path.home() / ".pulsetrader")

    @field_validator("rsi_overbought")
    @classmethod
    def _check_thresholds(cls, v: float, info) -> float:  # type: ignore[no-untyped-def]
        oversold = info.data.get("rsi_oversold", 30.0)
        if v <= oversold:
            raise ValueError("rsi_overbought must be > rsi_oversold")
        return v

    @property
    def state_file(self) -> Path:
        """Path to the persistent UI state JSON."""
        return self.state_dir / "state.json"

    @property
    def alert_state_file(self) -> Path:
        """Path to the persistent alert state JSON."""
        return self.state_dir / "alerts.json"


settings = Settings()
settings.state_dir.mkdir(parents=True, exist_ok=True)
