"""Signal generation logic based on technical indicators."""
from __future__ import annotations

from analytics.indicators import wilder_rsi
from config import settings
from models import Signal, SignalType


def generate_signal(ticker: str, closes: list[float]) -> Signal:
    """Evaluate price history and return a trading signal."""
    
    # Calculate RSI
    rsi = wilder_rsi(closes, period=settings.rsi_period)
    
    # If we don't have enough data yet to calculate RSI
    if rsi is None:
        return Signal(
            ticker=ticker,
            rsi=None,
            signal=SignalType.NA
        )
        
    # Determine the signal based on overbought/oversold thresholds
    if rsi <= settings.rsi_oversold:
        sig_type = SignalType.BUY
    elif rsi >= settings.rsi_overbought:
        sig_type = SignalType.SELL
    else:
        sig_type = SignalType.HOLD

    return Signal(
        ticker=ticker,
        rsi=rsi,
        signal=sig_type
    )