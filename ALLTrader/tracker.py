"""Async data orchestration. The single entry point for I/O — UI never calls APIs directly."""
from __future__ import annotations

import asyncio
import random
from collections import deque
from datetime import datetime, timezone
from typing import Iterable

import ccxt
import requests

from analytics.signals import generate_signal
from config import settings
from logging_config import logger
from models import ActivityEvent, AssetClass, Candle, Quote, Signal
from providers.base import DataProvider
from providers.crypto import CryptoProvider
from providers.stocks import StockProvider


class Tracker:
    """Owns the data lifecycle: fetch loop, rolling buffers, signals, activity log.

    The Streamlit UI reads from `snapshot()` only. All network I/O happens here.
    """

    # Exceptions we explicitly tolerate per fetch attempt.
    _SOFT_ERRORS = (
        ccxt.NetworkError,
        ccxt.ExchangeError,
        requests.RequestException,
        asyncio.TimeoutError,
    )

    def __init__(
        self,
        stocks: Iterable[str],
        cryptos: Iterable[str],
    ) -> None:
        self._stock_provider: DataProvider = StockProvider()
        self._crypto_provider: DataProvider = CryptoProvider()
        self._tickers: dict[str, AssetClass] = {}
        for s in stocks:
            self._tickers[s] = AssetClass.STOCK
        for c in cryptos:
            self._tickers[c] = AssetClass.CRYPTO

        self._quotes: dict[str, Quote] = {}
        self._signals: dict[str, Signal] = {}
        self._history: dict[str, deque[tuple[datetime, float, float]]] = {
            t: deque(maxlen=settings.chart_history_points) for t in self._tickers
        }
        self._closes: dict[str, deque[float]] = {
            t: deque(maxlen=max(settings.chart_history_points, 200))
            for t in self._tickers
        }
        self._failures: dict[str, int] = {t: 0 for t in self._tickers}
        self._backoff_until: dict[str, float] = {t: 0.0 for t in self._tickers}
        self._activity: deque[ActivityEvent] = deque(maxlen=200)
        self._lock = asyncio.Lock()
        self._running = False

    # ---------- lifecycle ----------
    async def warmup(self) -> None:
        """Seed close-price history so RSI is available from the first tick."""
        await asyncio.gather(
            *(self._seed_history(t, ac) for t, ac in self._tickers.items()),
            return_exceptions=True,
        )

    async def _seed_history(self, ticker: str, ac: AssetClass) -> None:
        provider = self._provider_for(ac)
        try:
            candles = await asyncio.wait_for(
                provider.fetch_candles(ticker, limit=120),
                timeout=settings.fetch_timeout_sec * 2,
            )
            for c in candles:
                self._closes[ticker].append(c.close)
                self._history[ticker].append((c.timestamp, c.close, c.volume))
            logger.info(f"warmup {ticker}: {len(candles)} candles loaded")
        except Exception as exc:
            logger.warning(f"warmup failed for {ticker}: {exc!r}")
            self._log_event(ticker, "error", f"warmup failed: {exc!r}")

    async def run_forever(self) -> None:
        """Drift-free fetch loop using monotonic scheduling."""
        self._running = True
        loop = asyncio.get_running_loop()
        next_tick = loop.time()
        while self._running:
            await self.tick()
            next_tick += settings.refresh_interval_sec
            sleep_for = max(0.0, next_tick - loop.time())
            if sleep_for == 0.0:
                # Fell behind — resync without piling up missed ticks.
                next_tick = loop.time()
            await asyncio.sleep(sleep_for)

    async def stop(self) -> None:
        self._running = False
        await self._stock_provider.close()
        await self._crypto_provider.close()

    # ---------- core tick ----------
    async def tick(self) -> None:
        """Fetch every ticker concurrently; update buffers, signals, activity log."""
        results = await asyncio.gather(
            *(self._fetch_one(t, ac) for t, ac in self._tickers.items()),
            return_exceptions=True,
        )
        async with self._lock:
            for (ticker, _), res in zip(self._tickers.items(), results):
                if isinstance(res, BaseException):
                    self._record_failure(ticker, res)
                elif res is not None:
                    self._record_success(ticker, res)

    async def _fetch_one(self, ticker: str, ac: AssetClass) -> Quote | None:
        loop = asyncio.get_running_loop()
        if loop.time() < self._backoff_until[ticker]:
            return None  # still in backoff
        provider = self._provider_for(ac)
        return await asyncio.wait_for(
            provider.fetch_quote(ticker),
            timeout=settings.fetch_timeout_sec,
        )

    def _record_success(self, ticker: str, quote: Quote) -> None:
        self._failures[ticker] = 0
        quote.is_stale = False
        self._quotes[ticker] = quote
        self._closes[ticker].append(quote.price)
        self._history[ticker].append(
            (quote.timestamp, quote.price, quote.volume_24h or 0.0)
        )
        self._signals[ticker] = generate_signal(ticker, list(self._closes[ticker]))

    def _record_failure(self, ticker: str, exc: BaseException) -> None:
        self._failures[ticker] += 1
        n = self._failures[ticker]
        # Exponential backoff with jitter.
        delay = min(settings.max_backoff_sec, 2 ** (n - 1)) + random.uniform(0, 0.5)
        loop = asyncio.get_event_loop()
        self._backoff_until[ticker] = loop.time() + delay

        msg = f"{type(exc).__name__}: {exc}"
        logger.error(f"fetch failure for {ticker} (#{n}): {msg}")
        self._log_event(ticker, "error", msg)

        if n >= settings.stale_threshold_failures and ticker in self._quotes:
            stale = self._quotes[ticker].model_copy(
                update={
                    "is_stale": True,
                    "consecutive_failures": n,
                    "last_error": msg,
                }
            )
            self._quotes[ticker] = stale

    # ---------- helpers ----------
    def _provider_for(self, ac: AssetClass) -> DataProvider:
        return self._stock_provider if ac == AssetClass.STOCK else self._crypto_provider

    def _log_event(self, ticker: str, event: str, details: str) -> None:
        self._activity.append(
            ActivityEvent(
                timestamp=datetime.now(timezone.utc),
                ticker=ticker,
                event=event,  # type: ignore[arg-type]
                details=details,
            )
        )

    # ---------- read API for the UI ----------
    def snapshot(self) -> dict:
        """Thread-safe-ish read of current state for the UI layer."""
        return {
            "quotes": dict(self._quotes),
            "signals": dict(self._signals),
            "history": {k: list(v) for k, v in self._history.items()},
            "activity": list(self._activity),
            "tickers": dict(self._tickers),
        }

    def add_activity(self, ticker: str, event: str, details: str) -> None:
        """Public hook so the alert engine can post into the same activity log."""
        self._log_event(ticker, event, details)
