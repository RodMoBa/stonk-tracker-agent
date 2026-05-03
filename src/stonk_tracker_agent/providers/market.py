from __future__ import annotations

from datetime import date
from typing import Any, Protocol

import requests


class MarketDataProvider(Protocol):
    def get_snapshot(self, symbol: str) -> dict[str, Any] | None:
        ...


class AlphaVantageMarketDataProvider:
    def __init__(self, api_key: str | None, timeout_seconds: int = 20):
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.base_url = "https://www.alphavantage.co/query"

    def get_snapshot(self, symbol: str) -> dict[str, Any] | None:
        if not self.api_key:
            return None
        price_payload = self._request({"function": "TIME_SERIES_DAILY", "symbol": symbol, "apikey": self.api_key})
        overview_payload = self._request({"function": "OVERVIEW", "symbol": symbol, "apikey": self.api_key})
        time_series = price_payload.get("Time Series (Daily)", {})
        if not time_series:
            return None
        latest_date = sorted(time_series.keys(), reverse=True)[0]
        latest = time_series[latest_date]
        return {
            "snapshot_date": date.fromisoformat(latest_date),
            "open_price": latest.get("1. open"),
            "high_price": latest.get("2. high"),
            "low_price": latest.get("3. low"),
            "close_price": latest.get("4. close"),
            "volume": int(float(latest.get("5. volume", 0))),
            "market_cap": overview_payload.get("MarketCapitalization"),
            "pe_ratio": overview_payload.get("PERatio"),
            "dividend_yield": overview_payload.get("DividendYield"),
            "raw_payload": {"price": price_payload, "overview": overview_payload},
        }

    def _request(self, params: dict[str, str]) -> dict[str, Any]:
        response = requests.get(self.base_url, params=params, timeout=self.timeout_seconds)
        response.raise_for_status()
        return response.json()


class NullMarketDataProvider:
    def get_snapshot(self, symbol: str) -> dict[str, Any] | None:
        return None

