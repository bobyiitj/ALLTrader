"""ccxt async crypto provider with primary + fallback exchanges."""
from __future__ import annotations

from datetime import datetime, timezone

import ccxt
import ccxt.async_support as ccxt_async

from config import settings
from logging_config import logger
from models import AssetClass, Candle, Quote
from providers.base import DataProvider


class CryptoProvider(DataProvider):
    """Wraps a primary ccxt exchange and falls back on hard failure."""

    def __init__(self) -> None:
        self._primary = self._build(settings.crypto_exchange)
        self._fallback = self._build(settings.crypto_fallback)

    @staticmethod
    def _build(name: str) -> ccxt_async.Exchange:
        if not hasattr(ccxt_async, name):
            raise ValueError(f"Unknown ccxt exchange: {name}")
        klass = getattr(ccxt_async, name)
        return klass({"enableRateLimit": True, "timeout": 8000})

    async def _try(self, exchange: ccxt_async.Exchange, op, *args, **kwargs):  # type: ignore[no-untyped-def]
        return await op(*args, **kwargs)

    async def fetch_quote(self, ticker: str) -> Quote:
        try:
            t = await self._primary.fetch_ticker(ticker)
        except (ccxt.NetworkError, ccxt.ExchangeError) as exc:
            logger.warning(
                f"primary {settings.crypto_exchange} failed for {ticker}: {exc!r}; "
                f"trying fallback {settings.crypto_fallback}"
            )
            t = await self._fallback.fetch_ticker(ticker)

        price = float(t.get("last") or t.get("close") or 0.0)
        if price <= 0:
            raise RuntimeError(f"Invalid price for {ticker}: {price}")

        return Quote(
            ticker=ticker,
            asset_class=AssetClass.CRYPTO,
            price=price,
            change_pct_24h=float(t["percentage"]) if t.get("percentage") is not None else None,
            volume_24h=float(t["quoteVolume"]) if t.get("quoteVolume") is not None else None,
            timestamp=datetime.now(timezone.utc),
        )

    async def fetch_candles(self, ticker: str, limit: int = 120) -> list[Candle]:
        try:
            ohlcv = await self._primary.fetch_ohlcv(ticker, "1m", limit=limit)
        except (ccxt.NetworkError, ccxt.ExchangeError) as exc:
            logger.warning(
                f"primary OHLCV failed for {ticker}: {exc!r}; using fallback"
            )
            ohlcv = await self._fallback.fetch_ohlcv(ticker, "1m", limit=limit)

        return [
            Candle(
                timestamp=datetime.fromtimestamp(row[0] / 1000, tz=timezone.utc),
                open=float(row[1]),
                high=float(row[2]),
                low=float(row[3]),
                close=float(row[4]),
                volume=float(row[5]),
            )
            for row in ohlcv
        ]

    async def close(self) -> None:
        for ex in (self._primary, self._fallback):
            try:
                await ex.close()
            except Exception as exc:  # pragma: no cover
                logger.warning(f"error closing exchange: {exc!r}")
