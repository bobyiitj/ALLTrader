"""Abstract DataProvider interface."""
from __future__ import annotations

from abc import ABC, abstractmethod

from models import Candle, Quote


class DataProvider(ABC):
    """Contract for any source that produces Quotes and historical Candles."""

    @abstractmethod
    async def fetch_quote(self, ticker: str) -> Quote:
        """Return the latest Quote for `ticker`. May raise on transport errors."""

    @abstractmethod
    async def fetch_candles(self, ticker: str, limit: int = 120) -> list[Candle]:
        """Return up to `limit` recent 1-minute candles, oldest first."""

    async def close(self) -> None:
        """Optional cleanup hook — e.g. for ccxt's aiohttp session."""
        return None
