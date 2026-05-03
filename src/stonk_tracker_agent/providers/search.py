from __future__ import annotations

from datetime import date
from typing import Any, Protocol

import requests


class SearchProvider(Protocol):
    def search_stock_news(self, *, symbol: str, company_name: str | None, days: int = 7) -> list[dict[str, Any]]:
        ...


class TavilySearchProvider:
    def __init__(self, api_key: str | None, timeout_seconds: int = 20):
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.base_url = "https://api.tavily.com/search"

    def search_stock_news(self, *, symbol: str, company_name: str | None, days: int = 7) -> list[dict[str, Any]]:
        if not self.api_key:
            return []
        query_name = company_name or symbol
        payload = {
            "api_key": self.api_key,
            "query": f"{query_name} {symbol} stock news catalyst last {days} days",
            "search_depth": "advanced",
            "topic": "news",
            "days": days,
            "max_results": 5,
            "include_answer": False,
        }
        response = requests.post(self.base_url, json=payload, timeout=self.timeout_seconds)
        response.raise_for_status()
        data = response.json()
        return [
            {
                "title": item.get("title"),
                "summary": item.get("content"),
                "source_url": item.get("url"),
                "source_name": item.get("source"),
                "event_date": date.today(),
                "raw_payload": item,
            }
            for item in data.get("results", [])
        ]


class NullSearchProvider:
    def search_stock_news(self, *, symbol: str, company_name: str | None, days: int = 7) -> list[dict[str, Any]]:
        return []

