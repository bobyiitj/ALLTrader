"""Unit tests for indicator math.

Reference values for Wilder's RSI come from the canonical example in
J. Welles Wilder, *New Concepts in Technical Trading Systems* (1978),
which is also the data set used in TA-Lib's regression tests.
"""
from __future__ import annotations

import math

import pytest

from analytics.indicators import ema, sma, wilder_rsi


# Wilder's original 14-period RSI example closes (rounded to 4dp in his book).
WILDER_CLOSES = [
    44.3389, 44.0902, 44.1497, 43.6124, 44.3278, 44.8264, 45.0955, 45.4245,
    45.8433, 46.0826, 45.8931, 46.0328, 45.6140, 46.2820, 46.2820, 46.0028,
    46.0328, 46.4116, 46.2222, 45.6439, 46.2122, 46.2521, 45.7137, 46.4515,
    45.7835, 45.3548, 44.0288, 44.1783, 44.2181, 44.5672, 43.4205, 42.6628,
    43.1314,
]
# Per Wilder, RSI at the last bar of this series is ~37.77.
WILDER_EXPECTED_LAST_RSI = 37.7733


def test_wilder_rsi_known_reference_series() -> None:
    rsi = wilder_rsi(WILDER_CLOSES, period=14)
    assert rsi is not None
    assert math.isclose(rsi, WILDER_EXPECTED_LAST_RSI, abs_tol=0.5), (
        f"RSI={rsi!r} not within tolerance of {WILDER_EXPECTED_LAST_RSI}"
    )


def test_wilder_rsi_insufficient_data_returns_none() -> None:
    assert wilder_rsi([1.0, 2.0, 3.0], period=14) is None
    assert wilder_rsi([], period=14) is None


def test_wilder_rsi_all_gains_returns_100() -> None:
    closes = [float(i) for i in range(1, 30)]
    rsi = wilder_rsi(closes, period=14)
    assert rsi == 100.0


def test_wilder_rsi_flat_series_handles_zero_loss() -> None:
    # All-equal closes: zero gain, zero loss → defined as 100.
    closes = [50.0] * 30
    rsi = wilder_rsi(closes, period=14)
    assert rsi == 100.0


def test_wilder_rsi_invalid_period_raises() -> None:
    with pytest.raises(ValueError):
        wilder_rsi([1.0, 2.0, 3.0], period=1)


def test_sma_and_ema_basic() -> None:
    vals = [1.0, 2.0, 3.0, 4.0, 5.0]
    assert sma(vals, 3) == pytest.approx(4.0)  # mean(3,4,5)
    assert sma(vals, 10) is None
    e = ema(vals, 3)
    assert e is not None and 2.5 < e < 5.0
