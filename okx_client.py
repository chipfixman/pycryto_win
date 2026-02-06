"""
OKX API v5 REST client: public (instruments, tickers, candles) and private (place/cancel order).
"""
import base64
import hashlib
import hmac
import json
from datetime import datetime, timezone
from typing import Any

import requests

from config import REST_BASE, API_KEY, SECRET_KEY, PASSPHRASE, USE_DEMO


def _timestamp_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _sign(timestamp: str, method: str, path: str, body: str = "") -> str:
    prehash = timestamp + method.upper() + path + body
    sig = hmac.new(
        SECRET_KEY.encode("utf-8"),
        prehash.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return base64.b64encode(sig).decode("utf-8")


def _request(
    method: str,
    path: str,
    params: dict[str, Any] | None = None,
    data: dict[str, Any] | None = None,
    private: bool = False,
) -> dict[str, Any]:
    url = REST_BASE.rstrip("/") + path
    params = params or {}
    body = ""
    if data is not None:
        body = json.dumps(data)
    qs = "&".join(f"{k}={v}" for k, v in sorted(params.items()) if v is not None and v != "")
    if qs:
        path_with_qs = path + "?" + qs
    else:
        path_with_qs = path
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if private and API_KEY and SECRET_KEY and PASSPHRASE:
        ts = _timestamp_iso()
        headers["OK-ACCESS-KEY"] = API_KEY
        headers["OK-ACCESS-SIGN"] = _sign(ts, method, path_with_qs, body)
        headers["OK-ACCESS-TIMESTAMP"] = ts
        headers["OK-ACCESS-PASSPHRASE"] = PASSPHRASE
    if USE_DEMO:
        headers["x-simulated-trading"] = "1"
    if method.upper() == "GET":
        r = requests.get(url, params=params, headers=headers, timeout=15)
    else:
        r = requests.post(url, json=data, headers=headers, timeout=15)
    r.raise_for_status()
    return r.json()


# --- Public ---

def get_instruments(inst_type: str = "SPOT") -> list[dict]:
    """GET /api/v5/public/instruments"""
    out = _request("GET", "/api/v5/public/instruments", {"instType": inst_type}, private=False)
    if out.get("code") != "0":
        raise RuntimeError(out.get("msg", "unknown error"))
    return out.get("data", [])


def get_tickers(inst_type: str = "SPOT") -> list[dict]:
    """GET /api/v5/market/tickers"""
    out = _request("GET", "/api/v5/market/tickers", {"instType": inst_type}, private=False)
    if out.get("code") != "0":
        raise RuntimeError(out.get("msg", "unknown error"))
    return out.get("data", [])


def get_candles(
    inst_id: str,
    bar: str = "1m",
    after: str | None = None,
    before: str | None = None,
    limit: str | int = "100",
) -> list[list]:
    """
    GET /api/v5/market/candles
    bar: 1m, 3m, 5m, 15m, 30m, 1H, 2H, 4H, 6H, 12H, 1D, 1W, 1M
    Returns list of [ts, o, h, l, c, vol, volCcy, volCcyQuote, confirm]
    """
    params = {"instId": inst_id, "bar": bar, "limit": str(limit)}
    if after:
        params["after"] = after
    if before:
        params["before"] = before
    out = _request("GET", "/api/v5/market/candles", params, private=False)
    if out.get("code") != "0":
        raise RuntimeError(out.get("msg", "unknown error"))
    return out.get("data", [])


# --- Private (trading) ---

def place_order(
    inst_id: str,
    side: str,
    ord_type: str,
    sz: str,
    px: str | None = None,
    td_mode: str = "cash",
) -> dict:
    """POST /api/v5/trade/order. ord_type: limit | market. side: buy | sell."""
    data = {
        "instId": inst_id,
        "tdMode": td_mode,
        "side": side,
        "ordType": ord_type,
        "sz": sz,
    }
    if ord_type == "limit" and px:
        data["px"] = px
    out = _request("POST", "/api/v5/trade/order", data=data, private=True)
    return out


def cancel_order(inst_id: str, ord_id: str) -> dict:
    """POST /api/v5/trade/cancel-order"""
    out = _request(
        "POST",
        "/api/v5/trade/cancel-order",
        data={"instId": inst_id, "ordId": ord_id},
        private=True,
    )
    return out


def get_orders(inst_type: str = "SPOT", inst_id: str | None = None) -> list[dict]:
    """GET /api/v5/trade/orders-pending"""
    params = {"instType": inst_type}
    if inst_id:
        params["instId"] = inst_id
    out = _request("GET", "/api/v5/trade/orders-pending", params=params, private=True)
    if out.get("code") != "0":
        raise RuntimeError(out.get("msg", "unknown error"))
    return out.get("data", [])


def get_balance(ccy: str | None = None) -> dict:
    """GET /api/v5/account/balance"""
    params = {}
    if ccy:
        params["ccy"] = ccy
    out = _request("GET", "/api/v5/account/balance", params=params or None, private=True)
    if out.get("code") != "0":
        raise RuntimeError(out.get("msg", "unknown error"))
    return out
