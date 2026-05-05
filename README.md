# ALLTrader

![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)

A real-time, multi-asset financial dashboard tracking equities (via **yfinance**) and cryptocurrencies (via **ccxt**) side-by-side. Built with Streamlit + asyncio for a non-blocking, production-quality UI.

## ✨ Features

- **Live prices** for stocks and crypto, refreshed every 10s (configurable)
- **Wilder RSI-based signals**: BUY / SELL / HOLD / N/A
- **Plotly charts** with selectable assets and time ranges
- **Smart desktop alerts** with debounced state machine — no notification spam
- **Resilient fetching** with exponential backoff, fallback exchange, stale-data UX
- **Persistent preferences** (targets, watchlist, refresh interval)
- **100% async I/O** — UI never blocks on network calls
- **Fully typed**, ruff-clean, mypy-strict, with unit tests

## 🛠 Install

```bash
git clone https://github.com/bobyiitj/ALLTrader.git
cd ALLTrader
python3.11 -m venv .venv && source .venv/bin/activate
make install
cp .env.example .env       # edit if you want
make run
```

## 🏗 Architecture

```text
┌────────────────────────────────────────────────────────────┐
│                       Streamlit (app.py)                    │
│   metrics · chart · sidebar · activity log · alerts UI      │
└──────────────────────────┬─────────────────────────────────┘
                           │ snapshot()  (read-only)
                           ▼
┌────────────────────────────────────────────────────────────┐
│                       Tracker (tracker.py)                  │
│   asyncio loop on daemon thread · rolling buffers · signals │
│   exponential backoff · stale-state machine                 │
└──────────┬──────────────────────────────────────┬──────────┘
           │                                      │
           ▼                                      ▼
   StockProvider (yfinance)              CryptoProvider (ccxt)
   sync calls in executor                async, primary+fallback
           │                                      │
           ▼                                      ▼
┌────────────────────────────────────────────────────────────┐
│            Analytics: indicators.py · signals.py            │
│            Alerts:   notifier.py (plyer + state machine)    │
└────────────────────────────────────────────────────────────┘
```

The **tracker thread** runs an `asyncio` event loop independent of Streamlit's script re-execution model. Streamlit triggers a periodic re-render via `streamlit-autorefresh` and reads a thread-safe snapshot of the latest prices and signals.

## ⚠️ Known limitations

- **yfinance rate limits**: Yahoo Finance throttles aggressive requests. The default 10s interval × 3 stocks is well within tolerance, but adding many tickers may trigger 429s.
- **Market hours**: Equity prices are stale outside US trading hours (the dashboard will correctly mark them via the change-pct value remaining unchanged, not as "stale" — that flag is for fetch errors).
- **Crypto exchange access**: Binance is geo-blocked in some regions (US in particular). Set `CRYPTO_EXCHANGE=kraken` (or `coinbase`) in `.env` if needed.
- **plyer on Linux**: requires `dbus`. On headless servers, OS notifications silently no-op; alerts still appear in the in-app activity log.
- **Single-process state**: Restarting the app reloads alerts but loses in-memory price history.

## 🧪 Testing

```bash
make test      # pytest
make lint      # ruff
make typecheck # mypy --strict
```