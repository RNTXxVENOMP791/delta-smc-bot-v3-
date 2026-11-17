import hashlib
import hmac
import json
import time
import requests
from urllib.parse import urlencode
from config import DEMO_BASE_URL, API_KEY, API_SECRET

class DeltaDemo:
    """Minimal Delta India Demo REST client. No production host is accepted."""
    def __init__(self):
        if "testnet" not in DEMO_BASE_URL:
            raise RuntimeError("Safety stop: only the official Demo/testnet host is allowed.")
        if not API_KEY or not API_SECRET:
            raise RuntimeError("Demo API credentials are missing. Configure them in the server environment.")
        self.base = DEMO_BASE_URL
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "delta-smc-human-approval-bot/3.0"
        })

    def _signed_headers(self, method, path, query, body):
        timestamp = str(int(time.time()))
        prehash = method.upper() + timestamp + path + query + body
        signature = hmac.new(API_SECRET.encode(), prehash.encode(), hashlib.sha256).hexdigest()
        return {"api-key": API_KEY, "timestamp": timestamp, "signature": signature}

    def request(self, method, path, params=None, payload=None):
        params = params or {}
        query = "?" + urlencode(sorted(params.items())) if params else ""
        body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False) if payload is not None else ""
        headers = self._signed_headers(method, path, query, body)
        response = self.session.request(
            method, self.base + path + query,
            data=body if body else None, headers=headers, timeout=20
        )
        response.raise_for_status()
        data = response.json()
        if data.get("success") is False:
            raise RuntimeError("Delta Demo API error: " + str(data))
        return data

    def products(self):
        response = self.session.get(self.base + "/v2/products", timeout=20,
                                    headers={"User-Agent": "delta-smc-human-approval-bot/3.0"})
        response.raise_for_status()
        return response.json()

    def place_market_entry(self, product_symbol, size, side, client_order_id):
        if side not in ("buy", "sell"):
            raise ValueError("Invalid order side.")
        if int(size) < 1:
            raise ValueError("Order size must be at least one contract.")
        payload = {
            "product_symbol": product_symbol,
            "size": int(size),
            "side": side,
            "order_type": "market_order",
            "time_in_force": "ioc",
            "client_order_id": client_order_id
        }
        return self.request("POST", "/v2/orders", payload=payload)
