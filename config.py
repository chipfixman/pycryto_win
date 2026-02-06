"""OKX API configuration. Set credentials in .env or edit defaults (demo trading)."""
import os

# OKX API v5
REST_BASE = "https://www.okx.com"
WS_PUBLIC = "wss://ws.okx.com:8443/ws/v5/public"
WS_PRIVATE = "wss://ws.okx.com:8443/ws/v5/private"

# Demo trading (same host; use x-simulated-trading: 1 header for REST)
# WS demo: wss://wspap.okx.com:8443/ws/v5/public and .../private
USE_DEMO = os.environ.get("OKX_DEMO", "1").strip().lower() in ("1", "true", "yes")
WS_PUBLIC_DEMO = "wss://wspap.okx.com:8443/ws/v5/public"
WS_PRIVATE_DEMO = "wss://wspap.okx.com:8443/ws/v5/private"

# Credentials (use env vars; never commit real keys)
API_KEY = os.environ.get("OKX_API_KEY", "")
SECRET_KEY = os.environ.get("OKX_SECRET_KEY", "")
PASSPHRASE = os.environ.get("OKX_PASSPHRASE", "")

def get_ws_public_url():
    return WS_PUBLIC_DEMO if USE_DEMO else WS_PUBLIC

def get_ws_private_url():
    return WS_PRIVATE_DEMO if USE_DEMO else WS_PRIVATE
