from __future__ import annotations

from datetime import date, datetime
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

    def search_stock_news(self, *, symbol: str, company_name: str | None, days: int = 30) -> list[dict[str, Any]]:
        if not self.api_key:
            return []
        query_name = company_name or symbol
        payload = {
            "api_key": self.api_key,
            "query": f"{query_name} {symbol} stock news catalyst last {days} days",
            "search_depth": "advanced",
            "topic": "news",
            "days": days,
            "max_results": 10,
            "include_answer": False,
        }
        response = requests.post(self.base_url, json=payload, timeout=self.timeout_seconds)
        response.raise_for_status()
        data = response.json()
        events = []
        for item in data.get("results", []):
            if not _is_relevant_result(item, symbol=symbol, company_name=company_name):
                continue
            events.append(
                {
                    "title": item.get("title"),
                    "summary": item.get("content"),
                    "source_url": item.get("url"),
                    "source_name": item.get("source"),
                    "event_date": _parse_event_date(item) or date.today(),
                    "raw_payload": item,
                }
            )
        return events


class NullSearchProvider:
    def search_stock_news(self, *, symbol: str, company_name: str | None, days: int = 30) -> list[dict[str, Any]]:
        return []


def _parse_event_date(item: dict[str, Any]) -> date | None:
    value = item.get("published_date") or item.get("published_at") or item.get("date")
    if not value:
        return None
    if isinstance(value, date):
        return value
    text = str(value).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            return None


def _is_relevant_result(item: dict[str, Any], *, symbol: str, company_name: str | None) -> bool:
    text = " ".join(
        str(value or "")
        for value in (
            item.get("title"),
            item.get("url"),
        )
    ).lower()
    if symbol.lower() in text:
        return True
    company_tokens = [token.lower() for token in (company_name or "").replace(",", " ").split() if len(token) > 2]
    return any(token in text for token in company_tokens)
