# OKX Crypto Desktop App

Python 3.12 + **wxPython** desktop application for OKX spot markets: view markets, live tickers, candles, and trade spot pairs via OKX REST API and WebSocket.

## Features

- **Markets**: List SPOT USDT pairs (from OKX REST), search/filter, select pair for detail and trading.
- **Tickers**: Live 24h tickers (REST load + WebSocket updates): last, change %, high/low, volume.
- **Candles**: OHLCV candlesticks (REST + WebSocket) with bar sizes: 1m, 3m, 5m, 15m, 30m, 1H, 2H, 4H, 1D.
- **Trading**: Place/cancel spot orders (limit or market) via REST; open orders list and WebSocket order updates when credentials are set.

## Requirements

- Python 3.12
- wxPython 4.2+
- requests, websocket-client

## Install

```bash
cd pycrypto_win
pip install -r requirements.txt
```

## Run

```bash
python app.py
```

Or:

```bash
python -m app
```

## Configuration

- **Demo trading** (default): No API keys needed for markets/tickers/candles. Set `OKX_DEMO=0` to use live.
- **Trading**: Set environment variables for OKX API v5:
  - `OKX_API_KEY`
  - `OKX_SECRET_KEY`
  - `OKX_PASSPHRASE`
  - For demo trading, create a Demo Trading API key on OKX and set `OKX_DEMO=1` (default).

Optional: copy `.env.example` to `.env` and set the variables (load `.env` in your shell or use a package like `python-dotenv` if you add it).

## OKX API

- REST: [OKX API v5](https://www.okx.com/docs-v5/en/)
- Public: instruments, tickers, candles.
- Private: place/cancel order, pending orders, balance (with API key).
- WebSocket: public tickers and candlestick channels; private orders channel (with login).

## License

MIT.
