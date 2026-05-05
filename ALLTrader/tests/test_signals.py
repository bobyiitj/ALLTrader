"""Tests for signal generation and the alert state machine."""
from __future__ import annotations

import time
from unittest.mock import patch

import pytest

from alerts.notifier import AlertEngine
from analytics.signals import generate_signal
from config import settings
from models import SignalType


@pytest.fixture(autouse=True)
def _isolate_alert_state(tmp_path, monkeypatch):
    """Redirect alert persistence to a temp dir for each test."""
    monkeypatch.setattr(settings, "state_dir", tmp_path)
    monkeypatch.setattr(
        type(settings),
        "alert_state_file",
        property(lambda self: tmp_path / "alerts.json"),
    )
    yield


def _series_with_drop(n: int = 30) -> list[float]:
    """Falling series → low RSI → BUY."""
    return [100.0 - i * 0.5 for i in range(n)]


def _series_with_rise(n: int = 30) -> list[float]:
    """Rising series → high RSI → SELL."""
    return [100.0 + i * 0.5 for i in range(n)]


def test_signal_buy_on_oversold() -> None:
    sig = generate_signal("TEST", _series_with_drop())
    assert sig.signal == SignalType.BUY


def test_signal_sell_on_overbought() -> None:
    sig = generate_signal("TEST", _series_with_rise())
    assert sig.signal == SignalType.SELL


def test_signal_na_when_insufficient_data() -> None:
    sig = generate_signal("TEST", [1.0, 2.0])
    assert sig.signal == SignalType.NA
    assert sig.rsi is None


def test_alert_fires_once_then_cools_down() -> None:
    fired: list[tuple[str, str, str]] = []
    engine = AlertEngine(on_event=lambda *a: fired.append(a))
    engine.set_alert("BTC/USDT", target_price=100.0, direction="above")

    with patch("alerts.notifier.notification.notify"):
        # First sample establishes baseline.
        assert engine.evaluate("BTC/USDT", 95.0) is False
        # Crossing upward → fire.
        assert engine.evaluate("BTC/USDT", 105.0) is True
        # Same tick again → cooldown blocks re-fire.
        assert engine.evaluate("BTC/USDT", 110.0) is False

    assert len(fired) == 1
    assert fired[0][1] == "alert"


def test_alert_re_arms_after_crossing_back() -> None:
    engine = AlertEngine()
    # Zero cooldown so we can verify the re-arm logic in isolation.
    object.__setattr__(settings, "alert_cooldown_sec", 0)
    engine.set_alert("BTC/USDT", target_price=100.0, direction="above")

    with patch("alerts.notifier.notification.notify"):
        engine.evaluate("BTC/USDT", 95.0)
        assert engine.evaluate("BTC/USDT", 105.0) is True   # fire
        # Price drops back below target → alert should re-arm (no fire on this tick).
        assert engine.evaluate("BTC/USDT", 90.0) is False
        time.sleep(0.01)
        # Cross again → fire again.
        assert engine.evaluate("BTC/USDT", 110.0) is True


def test_alert_below_direction_does_not_fire_on_upward_cross() -> None:
    engine = AlertEngine()
    engine.set_alert("BTC/USDT", target_price=100.0, direction="below")
    with patch("alerts.notifier.notification.notify"):
        engine.evaluate("BTC/USDT", 95.0)
        # 95 → 105 is upward; "below" alert ignores it.
        assert engine.evaluate("BTC/USDT", 105.0) is False
