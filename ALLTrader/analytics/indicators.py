"""Technical indicators — pure functions, no I/O, fully unit-testable."""
from __future__ import annotations

from collections.abc import Sequence

import numpy as np


def wilder_rsi(closes: Sequence[float], period: int = 14) -> float | None:
    """Compute Wilder's Relative Strength Index on a sequence of closes.

    Uses the canonical Wilder smoothing (a.k.a. RMA): the first average is a
    simple mean of the first `period` gains/losses, and subsequent averages
    are recursively smoothed:

        avg_gain_t = (avg_gain_{t-1} * (period - 1) + gain_t) / period

    This matches J. Welles Wilder's original 1978 definition (*New Concepts
    in Technical Trading Systems*) and the values produced by TradingView,
    Bloomberg, and TA-Lib's RSI function.

    Args:
        closes: Closing prices in chronological order (oldest first).
        period: Lookback period. Standard is 14.

    Returns:
        The RSI value (0–100) of the most recent bar, or None if there is
        insufficient data (need at least `period + 1` closes to produce one
        gain/loss observation per period).
    """
    if period < 2:
        raise ValueError("period must be >= 2")

    arr = np.asarray(closes, dtype=np.float64)
    if arr.size < period + 1:
        return None

    deltas = np.diff(arr)
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)

    # Seed: simple average over the first `period` deltas.
    avg_gain = gains[:period].mean()
    avg_loss = losses[:period].mean()

    # Wilder smoothing for everything after the seed.
    for i in range(period, deltas.size):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0:
        # All-up move — RSI is conventionally defined as 100 here.
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def sma(values: Sequence[float], period: int) -> float | None:
    """Simple moving average of the last `period` values."""
    if len(values) < period:
        return None
    return float(np.mean(values[-period:]))


def ema(values: Sequence[float], period: int) -> float | None:
    """Exponential moving average using the standard 2/(N+1) smoothing."""
    if len(values) < period:
        return None
    arr = np.asarray(values, dtype=np.float64)
    alpha = 2.0 / (period + 1.0)
    # Seed with SMA of first `period` values, then recurse.
    e = float(arr[:period].mean())
    for x in arr[period:]:
        e = alpha * x + (1 - alpha) * e
    return e
