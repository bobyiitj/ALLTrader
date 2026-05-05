"""yfinance-backed stock provider. Synchronous calls run in a thread pool."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pandas as pd
import yfinance as yf

from logging_config import logger
from models import AssetClass, Candle, Quote
from providers.base import DataProvider


class StockProvider(DataProvider):
    """yfinance is sync-only, so we run it in the default executor."""

    async def fetch_quote(self, ticker: str) -> Quote:
        loop = asyncio.get_running_loop()
        df: pd.DataFrame = await loop.run_in_executor(
            None, self._download_quote_df, ticker
        )
        if df.empty:
            raise RuntimeError(f"yfinance returned no data for {ticker}")

        last_close = float(df["Close"].iloc[-1])
        # 24h change: compare to the close ~1 trading day ago.
        try:
            prev = float(df["Close"].iloc[0])
            change_pct = (last_close - prev) / prev * 100.0 if prev else None
        except Exception:
            change_pct = None

        volume = float(df["Volume"].iloc[-1]) if "Volume" in df else None
        return Quote(
            ticker=ticker,
            asset_class=AssetClass.STOCK,
            price=last_close,
            change_pct_24h=change_pct,
            volume_24h=volume,
            timestamp=datetime.now(timezone.utc),
        )

    async def fetch_candles(self, ticker: str, limit: int = 120) -> list[Candle]:
        loop = asyncio.get_running_loop()
        df: pd.DataFrame = await loop.run_in_executor(
            None, self._download_candles_df, ticker
        )
        if df.empty:
            return []
        df = df.tail(limit)
        return [
            Candle(
                timestamp=ts.to_pydatetime().replace(tzinfo=timezone.utc)
                if ts.tzinfo is None
                else ts.to_pydatetime(),
                open=float(row["Open"]),
                high=float(row["High"]),
                low=float(row["Low"]),
                close=float(row["Close"]),
                volume=float(row.get("Volume", 0.0)),
            )
            for ts, row in df.iterrows()
        ]

    # --- private sync helpers (executed in thread pool) ---
    @staticmethod
    def _download_quote_df(ticker: str) -> pd.DataFrame:
        try:
            t = yf.Ticker(ticker)
            # 2 days @ 1m gives us enough data for 24h change + RSI seed.
            return t.history(period="2d", interval="1m", auto_adjust=False)
        except Exception as exc:
            logger.warning(f"yfinance quote failure for {ticker}: {exc!r}")
            raise

    @staticmethod
    def _download_candles_df(ticker: str) -> pd.DataFrame:
        try:
            t = yf.Ticker(ticker)
            return t.history(period="2d", interval="1m", auto_adjust=False)
        except Exception as exc:
            logger.warning(f"yfinance candles failure for {ticker}: {exc!r}")
            raise
