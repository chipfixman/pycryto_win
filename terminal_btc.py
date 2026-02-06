#!/usr/bin/env python3
"""
Single-file: OKX REST + WebSocket → BTC-USDT spot ticker, 1m candle, orderbook, trades.
Terminal UI via curses. Real-time updates.
Run: python terminal_btc.py
Quit: q or Esc

On Windows: pip install windows-curses  (curses not in stdlib).
"""
import json
import threading
import time
from datetime import datetime, timezone
from typing import Any

import requests
import websocket

try:
    import curses
except ImportError:
    curses = None

# --- Config (no external deps) ---
INST_ID = "BTC-USDT"
REST_BASE = "https://www.okx.com"
WS_URL = "wss://ws.okx.com:8443/ws/v5/public"

# --- Shared state (WS thread writes, main thread reads) ---
_state = {
    "ticker": {},
    "candle": [],   # [ts, o, h, l, c, vol, ...]
    "bids": [],     # [[price, sz, ...], ...]
    "asks": [],
    "trades": [],   # list of {price, sz, side, time, ...}
    "ts": 0,
    "error": "",
}
_lock = threading.Lock()


# --- REST ---
def _rest(path: str, params: dict[str, Any] | None = None) -> dict:
    url = REST_BASE.rstrip("/") + path
    r = requests.get(url, params=params or {}, timeout=10)
    r.raise_for_status()
    return r.json()


def fetch_ticker() -> dict:
    j = _rest("/api/v5/market/ticker", {"instId": INST_ID})
    if j.get("code") != "0":
        raise RuntimeError(j.get("msg", "ticker error"))
    return (j.get("data") or [{}])[0]


def fetch_candle_1m() -> list:
    j = _rest("/api/v5/market/candles", {"instId": INST_ID, "bar": "1m", "limit": "1"})
    if j.get("code") != "0":
        raise RuntimeError(j.get("msg", "candles error"))
    return (j.get("data") or [[]])[0] if j.get("data") else []


def fetch_orderbook() -> tuple[list, list]:
    j = _rest("/api/v5/market/books", {"instId": INST_ID, "sz": "20"})
    if j.get("code") != "0":
        raise RuntimeError(j.get("msg", "books error"))
    data = (j.get("data") or [{}])[0]
    return data.get("bids", []), data.get("asks", [])


def fetch_trades() -> list:
    j = _rest("/api/v5/market/trades", {"instId": INST_ID, "limit": "20"})
    if j.get("code") != "0":
        raise RuntimeError(j.get("msg", "trades error"))
    return j.get("data", [])


# --- WebSocket ---
def _on_ws_message(ws, raw: str):
    if raw == "pong":
        return
    try:
        data = json.loads(raw)
        if "event" in data:
            return
        arg = data.get("arg", {})
        ch = arg.get("channel", "")
        payload = data.get("data", [])
        with _lock:
            _state["ts"] = time.time()
            if ch == "tickers" and payload:
                _state["ticker"] = payload[0] if isinstance(payload[0], dict) else {}
            elif ch == "candle1m" and payload:
                c = payload[0]
                _state["candle"] = c if isinstance(c, list) else []
            elif ch == "books5" and payload:
                d = payload[0]
                if isinstance(d, dict):
                    _state["bids"] = d.get("bids", [])[:10]
                    _state["asks"] = d.get("asks", [])[:10]
            elif ch == "books" and payload:
                d = payload[0]
                if isinstance(d, dict):
                    _state["bids"] = d.get("bids", [])[:15]
                    _state["asks"] = d.get("asks", [])[:15]
            elif ch == "trades" and payload:
                # New trades at front; keep last 30
                new_ = [t if isinstance(t, dict) else {} for t in payload]
                _state["trades"] = (new_ + _state["trades"])[:30]
    except Exception as e:
        with _lock:
            _state["error"] = str(e)


def _ws_thread():
    ws = websocket.WebSocketApp(
        WS_URL,
        on_open=lambda w: _ws_send_subs(w),
        on_message=_on_ws_message,
        on_error=lambda w, e: None,
    )
    while True:
        try:
            ws.run_forever(ping_interval=25, ping_timeout=10)
        except Exception:
            pass
        time.sleep(3)


def _ws_send_subs(ws):
    for ch, arg in [
        ("tickers", {"channel": "tickers", "instId": INST_ID}),
        ("candle1m", {"channel": "candle1m", "instId": INST_ID}),
        ("books5", {"channel": "books5", "instId": INST_ID}),
        ("trades", {"channel": "trades", "instId": INST_ID}),
    ]:
        ws.send(json.dumps({"op": "subscribe", "args": [arg]}))


# --- Curses UI ---
def _fmt_ts(ts_ms) -> str:
    try:
        return datetime.fromtimestamp(int(ts_ms) / 1000, tz=timezone.utc).strftime("%H:%M:%S")
    except Exception:
        return str(ts_ms)


def _draw_ticker(win, h: int, w: int):
    with _lock:
        t = _state["ticker"]
    win.erase()
    win.border()
    win.addstr(0, 2, f" {INST_ID} Ticker ", curses.A_REVERSE)
    if not t:
        win.addstr(2, 2, "Waiting for data...")
        return
    last = t.get("last", "") or t.get("lastPx", "")
    open24 = t.get("open24h", "") or t.get("sodUtc0", "") or "0"
    try:
        ch = (float(last) - float(open24)) / float(open24) * 100 if float(open24) else 0
        ch_str = f"{ch:+.2f}%"
    except (TypeError, ValueError):
        ch_str = "—"
    vol = t.get("vol24h", "") or t.get("volCcy24h", "")
    win.addstr(1, 2, f" Last: {last}")
    win.addstr(2, 2, f" 24h:  O {open24}  Change {ch_str}")
    win.addstr(3, 2, f" High: {t.get('high24h') or t.get('highPx', '')}  Low: {t.get('low24h') or t.get('lowPx', '')}")
    win.addstr(4, 2, f" Vol24h: {vol[:20]}" if vol else " Vol24h: —")
    win.noutrefresh()


def _draw_candle(win, h: int, w: int):
    with _lock:
        c = _state["candle"]
    win.erase()
    win.border()
    win.addstr(0, 2, f" Candle 1m ", curses.A_REVERSE)
    if not c or len(c) < 5:
        win.addstr(2, 2, "Waiting for data...")
        return
    ts, o, hi, lo, cl = c[0], c[1], c[2], c[3], c[4]
    vol = c[5] if len(c) > 5 else ""
    win.addstr(1, 2, f" Time: {_fmt_ts(ts)}")
    win.addstr(2, 2, f" O: {o}   H: {hi}   L: {lo}   C: {cl}")
    win.addstr(3, 2, f" Vol: {vol}")
    win.noutrefresh()


def _draw_orderbook(win, h: int, w: int):
    with _lock:
        bids, asks = _state["bids"], _state["asks"]
    win.erase()
    win.border()
    win.addstr(0, 2, f" Orderbook ", curses.A_REVERSE)
    win.addstr(1, 2, "  Price", curses.A_BOLD)
    win.addstr(1, min(24, w - 14), "Size", curses.A_BOLD)
    row = 2
    for level in (asks[:8] if asks else []):
        price = level[0] if len(level) > 0 else ""
        sz = level[1] if len(level) > 1 else ""
        if row >= h - 2:
            break
        win.addstr(row, 2, f"  {price}", curses.color_pair(2) if hasattr(curses, "color_pair") else 0)
        win.addstr(row, min(24, w - 12), str(sz)[:12])
        row += 1
    if row < h - 2:
        win.addstr(row, 2, "  ---")
        row += 1
    for level in (bids[:8] if bids else []):
        price = level[0] if len(level) > 0 else ""
        sz = level[1] if len(level) > 1 else ""
        if row >= h - 2:
            break
        win.addstr(row, 2, f"  {price}", curses.color_pair(1) if hasattr(curses, "color_pair") else 0)
        win.addstr(row, min(24, w - 12), str(sz)[:12])
        row += 1
    if not bids and not asks:
        win.addstr(2, 2, "Waiting for data...")
    win.noutrefresh()


def _draw_trades(win, h: int, w: int):
    with _lock:
        trades = list(_state["trades"][:h - 3])
    win.erase()
    win.border()
    win.addstr(0, 2, f" Trades ", curses.A_REVERSE)
    win.addstr(1, 2, " Time   Side   Price    Size")
    for i, t in enumerate(trades):
        if i + 2 >= h - 1:
            break
        tm = _fmt_ts(t.get("ts", ""))
        side = (t.get("side") or "—")[:4]
        px = t.get("px") or t.get("price", "—")
        sz = t.get("sz") or t.get("size", "—")
        attr = curses.A_NORMAL
        if hasattr(curses, "color_pair"):
            attr = curses.color_pair(1) if side.lower() == "buy" else curses.color_pair(2)
        win.addstr(2 + i, 2, f" {tm}  {side:4}  {str(px):>10}  {str(sz)[:12]}", attr)
    if not trades:
        win.addstr(2, 2, "Waiting for data...")
    win.noutrefresh()


def _run_curses(stdscr):
    curses.curs_set(0)
    if hasattr(curses, "use_default_colors"):
        try:
            curses.use_default_colors()
        except Exception:
            pass
    if hasattr(curses, "init_pair"):
        try:
            curses.init_pair(1, curses.COLOR_GREEN, -1)
            curses.init_pair(2, curses.COLOR_RED, -1)
        except Exception:
            pass
    stdscr.clear()
    stdscr.refresh()
    h, w = stdscr.getmaxyx()
    # Four quadrants
    th, tw = max(8, h // 2), max(40, w // 2)
    y2 = th + 1
    h2 = h - th - 2
    w2 = w - tw - 2
    win_ticker = curses.newwin(th, tw, 0, 0)
    win_candle = curses.newwin(th, w2, 0, tw + 1)
    win_book = curses.newwin(h2, tw, y2, 0)
    win_trades = curses.newwin(h2, w2, y2, tw + 1)
    # Initial REST load
    try:
        with _lock:
            _state["ticker"] = fetch_ticker()
            c = fetch_candle_1m()
            _state["candle"] = c if c else _state["candle"]
            b, a = fetch_orderbook()
            _state["bids"], _state["asks"] = b, a
            _state["trades"] = fetch_trades() or _state["trades"]
    except Exception as e:
        with _lock:
            _state["error"] = str(e)
    # WS thread
    t = threading.Thread(target=_ws_thread, daemon=True)
    t.start()
    # Refresh loop
    while True:
        try:
            nh, nw = stdscr.getmaxyx()
            if nh != h or nw != w:
                h, w = nh, nw
                th, tw = max(8, h // 2), max(40, w // 2)
                y2 = th + 1
                h2 = h - th - 2
                w2 = w - tw - 2
                win_ticker = curses.newwin(th, tw, 0, 0)
                win_candle = curses.newwin(th, w2, 0, tw + 1)
                win_book = curses.newwin(h2, tw, y2, 0)
                win_trades = curses.newwin(h2, w2, y2, tw + 1)
            _draw_ticker(win_ticker, th, tw)
            _draw_candle(win_candle, th, w2)
            _draw_orderbook(win_book, h2, tw)
            _draw_trades(win_trades, h2, w2)
            curses.doupdate()
            with _lock:
                err = _state.get("error", "")
            if err:
                stdscr.addstr(h - 1, 0, f" WS: {err[:w-6]} ".ljust(w)[:w], curses.A_REVERSE)
                _state["error"] = ""
            c = stdscr.getch()
            if c == ord("q") or c == 27:
                break
        except curses.error:
            pass


def main():
    if not curses:
        print("Install curses (e.g. pip install windows-curses on Windows)")
        return
    try:
        curses.wrapper(_run_curses)
    except KeyboardInterrupt:
        pass
    print("Bye.")


if __name__ == "__main__":
    main()
