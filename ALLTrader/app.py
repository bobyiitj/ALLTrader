"""Streamlit UI — presentation only. All data flows through Tracker."""
from __future__ import annotations

import asyncio
import json
import threading
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots
from streamlit_autorefresh import st_autorefresh

from alerts.notifier import AlertEngine
from config import settings
from logging_config import configure_logging, logger
from models import AssetClass, SignalType
from tracker import Tracker

configure_logging()

st.set_page_config(
    page_title="AllTrader",
    page_icon="",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Background tracker thread
# ---------------------------------------------------------------------------
# Streamlit re-runs the script top-to-bottom on every interaction. We must
# therefore start the async tracker once and store it on a module-level
# singleton, NOT in st.session_state (which is per-session).


@st.cache_resource(show_spinner="Starting market data engine…")
def get_tracker() -> Tracker:
    """Create the Tracker once and run its event loop on a daemon thread."""
    tracker = Tracker(
        stocks=list(settings.default_stocks),
        cryptos=list(settings.default_cryptos),
    )

    def _run() -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(tracker.warmup())
            loop.run_until_complete(tracker.run_forever())
        except Exception as exc:  # pragma: no cover
            logger.exception(f"tracker thread crashed: {exc!r}")

    threading.Thread(target=_run, name="pulsetrader-loop", daemon=True).start()
    return tracker


@st.cache_resource
def get_alert_engine(_tracker: Tracker) -> AlertEngine:
    """One AlertEngine for the whole app, wired into the tracker's activity log."""
    return AlertEngine(on_event=_tracker.add_activity)


tracker = get_tracker()
alerts = get_alert_engine(tracker)


# ---------------------------------------------------------------------------
# Persistent UI state
# ---------------------------------------------------------------------------
def _load_ui_state() -> dict:
    p: Path = settings.state_file
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:
            return {}
    return {}


def _save_ui_state(state: dict) -> None:
    try:
        settings.state_file.write_text(json.dumps(state, indent=2))
    except Exception as exc:
        logger.warning(f"could not save UI state: {exc!r}")


if "ui_loaded" not in st.session_state:
    persisted = _load_ui_state()
    st.session_state.targets = persisted.get("targets", {})
    st.session_state.directions = persisted.get("directions", {})
    st.session_state.refresh_sec = persisted.get("refresh_sec", settings.refresh_interval_sec)
    st.session_state.paused = False
    st.session_state.ui_loaded = True


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.title("ALLTrader")
    st.caption("Real-time multi-asset dashboard")

    snap = tracker.snapshot()
    all_tickers = list(snap["tickers"].keys())

    st.subheader("🔔 Alerts")
    for ticker in all_tickers:
        with st.expander(ticker, expanded=False):
            current_target = st.session_state.targets.get(ticker, 0.0)
            current_dir = st.session_state.directions.get(ticker, "either")

            target = st.number_input(
                "Target price",
                min_value=0.0,
                value=float(current_target),
                step=0.01,
                key=f"tgt_{ticker}",
                format="%.4f",
            )
            direction = st.selectbox(
                "Direction",
                options=["above", "below", "either"],
                index=["above", "below", "either"].index(current_dir),
                key=f"dir_{ticker}",
            )
            st.session_state.targets[ticker] = target
            st.session_state.directions[ticker] = direction
            alerts.set_alert(
                ticker,
                target if target > 0 else None,
                direction,
            )

    st.subheader("⏱️ Refresh")
    st.session_state.refresh_sec = st.slider(
        "Interval (seconds)",
        min_value=5,
        max_value=60,
        value=int(st.session_state.refresh_sec),
        step=1,
    )
    st.session_state.paused = st.toggle("⏸ Pause updates", value=st.session_state.paused)

    if st.button("💾 Save preferences"):
        _save_ui_state(
            {
                "targets": st.session_state.targets,
                "directions": st.session_state.directions,
                "refresh_sec": st.session_state.refresh_sec,
            }
        )
        st.success("Preferences saved.")


# ---------------------------------------------------------------------------
# Auto-refresh
# ---------------------------------------------------------------------------
if not st.session_state.paused:
    st_autorefresh(interval=st.session_state.refresh_sec * 1000, key="pulsetick")

# ---------------------------------------------------------------------------
# Main area
# ---------------------------------------------------------------------------
snap = tracker.snapshot()
quotes = snap["quotes"]
signals = snap["signals"]
history = snap["history"]
activity = snap["activity"]

st.title("ALLTrader Dashboard")
st.caption(
    "_For educational purposes only — not financial advice._  "
    f"Tracking {len(snap['tickers'])} assets · "
    f"refresh every {st.session_state.refresh_sec}s"
    + ("  ·  ⏸ **PAUSED**" if st.session_state.paused else "")
)

# --- Metric cards ----------------------------------------------------------
SIGNAL_EMOJI = {
    SignalType.BUY: "🟢 BUY",
    SignalType.SELL: "🔴 SELL",
    SignalType.HOLD: "🟡 HOLD",
    SignalType.NA: "⚪ N/A",
}

cols = st.columns(len(snap["tickers"]) or 1)
for col, ticker in zip(cols, snap["tickers"]):
    q = quotes.get(ticker)
    sig = signals.get(ticker)
    with col:
        if q is None:
            st.metric(ticker, "—", help="awaiting first quote")
            continue
        label = ticker + (" ⚠️" if q.is_stale else "")
        delta = (
            f"{q.change_pct_24h:+.2f}%"
            if q.change_pct_24h is not None
            else None
        )
        st.metric(label, f"{q.price:,.4f}", delta=delta)
        st.caption(SIGNAL_EMOJI[sig.signal] if sig else "⚪ N/A")
        if sig and sig.rsi is not None:
            st.caption(f"RSI: {sig.rsi:.2f}")
        if q.is_stale and q.last_error:
            st.caption(f":orange[stale · {q.last_error[:50]}]")

# --- Evaluate alerts on every render --------------------------------------
for ticker, q in quotes.items():
    if not q.is_stale:
        alerts.evaluate(ticker, q.price)

# --- Chart ----------------------------------------------------------------
st.divider()
st.subheader("📊 Price chart")

selected = st.multiselect(
    "Assets",
    options=list(snap["tickers"].keys()),
    default=list(snap["tickers"].keys())[:3],
)

range_choice = st.radio(
    "Range",
    options=["5m", "15m", "1h", "All"],
    horizontal=True,
    index=3,
)
range_points = {"5m": 5, "15m": 15, "1h": 60, "All": settings.chart_history_points}[range_choice]

fig = make_subplots(specs=[[{"secondary_y": True}]])
for ticker in selected:
    rows = history.get(ticker, [])[-range_points:]
    if not rows:
        continue
    df = pd.DataFrame(rows, columns=["ts", "price", "volume"])
    fig.add_trace(
        go.Scatter(x=df["ts"], y=df["price"], mode="lines", name=ticker),
        secondary_y=False,
    )

fig.update_layout(
    height=480,
    margin=dict(l=10, r=10, t=30, b=10),
    legend=dict(orientation="h", yanchor="bottom", y=1.02),
    hovermode="x unified",
)
fig.update_yaxes(title_text="Price", secondary_y=False)
st.plotly_chart(fig, use_container_width=True)

# --- Activity log ---------------------------------------------------------
st.divider()
st.subheader("📜 Activity log")

if activity:
    df = pd.DataFrame(
        [
            {
                "time": ev.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                "ticker": ev.ticker,
                "event": ev.event,
                "details": ev.details,
            }
            for ev in reversed(activity)
        ]
    )
    st.dataframe(df, use_container_width=True, height=240, hide_index=True)
else:
    st.info("No events yet.")
