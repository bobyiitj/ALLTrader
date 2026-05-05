"""Plyer-backed desktop notifier with a debounced alert state machine."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Callable

from plyer import notification

from config import settings
from logging_config import logger
from models import Alert


class AlertEngine:
    """Manages the lifecycle of price alerts: armed → fired → cooldown → re-armed."""

    def __init__(self, on_event: Callable[[str, str, str], None] | None = None) -> None:
        """
        Args:
            on_event: Optional callback(ticker, event_type, details) for activity log.
        """
        self._alerts: dict[str, Alert] = {}
        self._on_event = on_event
        self._load()

    # ---------- public API ----------
    def set_alert(
        self,
        ticker: str,
        target_price: float | None,
        direction: str = "either",
    ) -> None:
        """Create / update / remove an alert for `ticker`.

        Passing target_price=None removes the alert.
        """
        if target_price is None or target_price <= 0:
            self._alerts.pop(ticker, None)
        else:
            existing = self._alerts.get(ticker)
            self._alerts[ticker] = Alert(
                ticker=ticker,
                target_price=float(target_price),
                direction=direction,  # type: ignore[arg-type]
                armed=True,
                last_fired=existing.last_fired if existing else None,
                last_price_seen=existing.last_price_seen if existing else None,
            )
        self._persist()

    def get_alert(self, ticker: str) -> Alert | None:
        return self._alerts.get(ticker)

    def evaluate(self, ticker: str, current_price: float) -> bool:
        """Check whether `current_price` triggers the alert for `ticker`.

        Returns True if a notification was fired this tick.
        """
        alert = self._alerts.get(ticker)
        if alert is None:
            return False

        prev = alert.last_price_seen
        alert.last_price_seen = current_price

        # Cooldown check.
        if alert.last_fired is not None:
            cooldown = timedelta(seconds=settings.alert_cooldown_sec)
            if datetime.now(timezone.utc) - alert.last_fired < cooldown:
                self._persist()
                return False

        if not alert.armed:
            # Re-arm if price moved back across the threshold.
            if prev is not None and self._crossed_back(alert, prev, current_price):
                alert.armed = True
            self._persist()
            return False

        if prev is None:
            self._persist()
            return False  # need two samples to detect a crossing

        if self._crossed(alert, prev, current_price):
            self._fire(alert, current_price)
            alert.armed = False
            alert.last_fired = datetime.now(timezone.utc)
            self._persist()
            return True

        self._persist()
        return False

    # ---------- internals ----------
    @staticmethod
    def _crossed(alert: Alert, prev: float, curr: float) -> bool:
        tgt = alert.target_price
        if alert.direction == "above":
            return prev < tgt <= curr
        if alert.direction == "below":
            return prev > tgt >= curr
        # either
        return (prev < tgt <= curr) or (prev > tgt >= curr)

    @staticmethod
    def _crossed_back(alert: Alert, prev: float, curr: float) -> bool:
        """Opposite direction of the original trigger — re-arms the alert."""
        tgt = alert.target_price
        if alert.direction == "above":
            return prev >= tgt > curr
        if alert.direction == "below":
            return prev <= tgt < curr
        return (prev >= tgt > curr) or (prev <= tgt < curr)

    def _fire(self, alert: Alert, current_price: float) -> None:
        title = f"PulseTrader • {alert.ticker}"
        msg = (
            f"{alert.ticker} hit {current_price:.4f} "
            f"(target {alert.target_price:.4f}, {alert.direction})"
        )
        try:
            notification.notify(
                title=title,
                message=msg,
                app_name="PulseTrader",
                timeout=10,
            )
        except Exception as exc:
            # plyer often fails on headless Linux without dbus.
            logger.warning(f"plyer notify failed for {alert.ticker}: {exc!r}")

        logger.info(f"ALERT FIRED: {msg}")
        if self._on_event:
            self._on_event(alert.ticker, "alert", msg)

    def _persist(self) -> None:
        try:
            payload = {
                k: v.model_dump(mode="json") for k, v in self._alerts.items()
            }
            settings.alert_state_file.write_text(json.dumps(payload, indent=2, default=str))
        except Exception as exc:
            logger.warning(f"could not persist alerts: {exc!r}")

    def _load(self) -> None:
        path = settings.alert_state_file
        if not path.exists():
            return
        try:
            raw = json.loads(path.read_text())
            for k, v in raw.items():
                self._alerts[k] = Alert.model_validate(v)
        except Exception as exc:
            logger.warning(f"could not load alerts: {exc!r}")
