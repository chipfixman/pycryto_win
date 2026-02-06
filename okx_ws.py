"""
OKX API v5 WebSocket client: public (tickers, candlestick) and private (login, orders).
Runs in a background thread; callbacks receive parsed data.
"""
import base64
import hashlib
import hmac
import json
import threading
import time
from typing import Any, Callable

import websocket

from config import get_ws_public_url, get_ws_private_url, API_KEY, SECRET_KEY, PASSPHRASE


def _sign_ws(timestamp: str) -> str:
    msg = timestamp + "GET" + "/users/self/verify"
    sig = hmac.new(
        SECRET_KEY.encode("utf-8"),
        msg.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return base64.b64encode(sig).decode("utf-8")


class OKXWebSocket:
    """Single connection: public or private. Subscribe and receive via callbacks."""

    def __init__(
        self,
        private: bool = False,
        on_message: Callable[[dict], None] | None = None,
        on_error: Callable[[Exception], None] | None = None,
        on_open: Callable[[], None] | None = None,
    ):
        self.private = private
        self.on_message = on_message or (lambda _: None)
        self.on_error = on_error or (lambda _: None)
        self.on_open = on_open or (lambda: None)
        self._ws: websocket.WebSocketApp | None = None
        self._thread: threading.Thread | None = None
        self._running = False
        self._last_pong = 0.0

    def _run(self):
        url = get_ws_private_url() if self.private else get_ws_public_url()
        self._ws = websocket.WebSocketApp(
            url,
            on_open=self._on_open,
            on_message=self._on_message,
            on_error=lambda ws, err: self.on_error(err),
            on_close=lambda ws, code, msg: None,
        )
        self._running = True
        self._ws.run_forever(ping_interval=25, ping_timeout=10)
        self._running = False

    def _on_open(self, ws):
        if self.private and API_KEY and SECRET_KEY and PASSPHRASE:
            ts = str(int(time.time()))
            sign = _sign_ws(ts)
            ws.send(
                json.dumps(
                    {
                        "op": "login",
                        "args": [
                            {
                                "apiKey": API_KEY,
                                "passphrase": PASSPHRASE,
                                "timestamp": ts,
                                "sign": sign,
                            }
                        ],
                    }
                )
            )
        self.on_open()

    def _on_message(self, ws, raw: str):
        try:
            if raw == "pong":
                self._last_pong = time.time()
                return
            data = json.loads(raw)
            if "event" in data:
                # subscribe/unsubscribe/login etc
                if data.get("event") == "login" and data.get("code") != "0":
                    self.on_error(RuntimeError(data.get("msg", "Login failed")))
                return
            if "data" in data and isinstance(data["data"], list):
                for item in data["data"]:
                    self.on_message({"arg": data.get("arg", {}), "data": item})
            else:
                self.on_message(data)
        except Exception as e:
            self.on_error(e)

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._ws:
            try:
                self._ws.close()
            except Exception:
                pass
            self._ws = None

    def send(self, obj: dict):
        if self._ws and self._running:
            try:
                self._ws.send(json.dumps(obj))
            except Exception as e:
                self.on_error(e)

    def subscribe_ticker(self, inst_id: str):
        self.send({"op": "subscribe", "args": [{"channel": "tickers", "instId": inst_id}]})

    def unsubscribe_ticker(self, inst_id: str):
        self.send({"op": "unsubscribe", "args": [{"channel": "tickers", "instId": inst_id}]})

    def subscribe_candle(self, inst_id: str, bar: str = "1m"):
        # channel: candle + bar e.g. candle1m
        channel = "candle" + bar
        self.send({"op": "subscribe", "args": [{"channel": channel, "instId": inst_id}]})

    def unsubscribe_candle(self, inst_id: str, bar: str = "1m"):
        channel = "candle" + bar
        self.send({"op": "unsubscribe", "args": [{"channel": channel, "instId": inst_id}]})

    def subscribe_orders(self, inst_type: str = "SPOT"):
        self.send({"op": "subscribe", "args": [{"channel": "orders", "instType": inst_type}]})

    def place_order_ws(self, inst_id: str, side: str, ord_type: str, sz: str, px: str | None = None, td_mode: str = "cash"):
        args = {"instId": inst_id, "tdMode": td_mode, "side": side, "ordType": ord_type, "sz": sz}
        if ord_type == "limit" and px:
            args["px"] = px
        self.send({"op": "order", "args": [args]})

    def cancel_order_ws(self, inst_id: str, ord_id: str):
        self.send({"op": "cancel-order", "args": [{"instId": inst_id, "ordId": ord_id}]})
