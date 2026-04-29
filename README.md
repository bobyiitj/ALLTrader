# ALLTrader

A real-time, multi-asset financial dashboard tracking equities (via **yfinance**) and cryptocurrencies (via **ccxt**) side-by-side. Built with Streamlit + asyncio for a non-blocking, production-quality monitoring experience.

> ⚠️ **Disclaimer:** This software is for **educational purposes only**. It is **not financial advice**. Do not use it to make trading decisions. Past performance does not guarantee future results.

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
git clone <your-repo>
cd pulsetrader
python3.11 -m venv .venv && source .venv/bin/activate
make install
cp .env.example .env       # edit if you want
make run
```

Open http://localhost:8501.

## 🏗 Architecture

```
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

The **tracker thread** runs an `asyncio` event loop independent of Streamlit's script re-execution model. Streamlit triggers a periodic re-render via `streamlit-autorefresh` and reads a thread-safe snapshot from the tracker — there is no shared mutable state crossing the boundary.

## ⚠️ Known limitations

- **yfinance rate limits**: Yahoo Finance throttles aggressive requests. The default 10s interval × 3 stocks is well within tolerance, but adding many tickers may trigger 429s.
- **Market hours**: Equity prices are stale outside US trading hours (the dashboard will correctly mark them via the change-pct value remaining unchanged, not as "stale" — that flag is for fetch failures).
- **Crypto exchange access**: Binance is geo-blocked in some regions (US in particular). Set `CRYPTO_EXCHANGE=kraken` (or `coinbase`) in `.env` if needed.
- **plyer on Linux**: requires `dbus`. On headless servers, OS notifications silently no-op; alerts still appear in the in-app activity log.
- **Single-process state**: Restarting the app reloads alerts but loses in-memory price history.

## 🧪 Testing

```bash
make test      # pytest
make lint      # ruff
make typecheck # mypy --strict
```

## 📄 License

MIT.
