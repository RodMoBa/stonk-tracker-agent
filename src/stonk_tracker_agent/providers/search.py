from __future__ import annotations

from datetime import date, datetime
from typing import Any, Protocol

import requests

NAVIGATION_JUNK_PHRASES = {
    "skip navigation",
    "watch now",
    "pre-markets",
    "u.s. markets",
    "europe markets",
    "asia markets",
    "world markets",
    "currencies",
    "prediction markets",
    "cryptocurrency",
    "futures & commodities",
    "funds & etfs",
    "white house policy",
    "squawk box",
}

GENERIC_NAV_HEADLINES = {
    "markets",
    "business",
    "investing",
    "tech",
    "politics",
    "video",
    "share",
}


class SearchProvider(Protocol):
    def search_stock_news(self, *, symbol: str, company_name: str | None, days: int = 7) -> list[dict[str, Any]]:
        ...

    def search_market_context(
        self,
        *,
        query: str,
        days: int = 30,
        max_results: int = 8,
        topic: str = "news",
    ) -> list[dict[str, Any]]:
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
            "query": f"{query_name} {symbol} stock news headlines catalysts last {days} days",
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
            if _looks_like_navigation_junk(item):
                continue
            if not _is_relevant_result(item, symbol=symbol, company_name=company_name):
                continue
            events.append(
                {
                    "title": _clean_headline(item.get("title")) or "Untitled event",
                    "summary": None,
                    "source_url": item.get("url"),
                    "source_name": item.get("source"),
                    "event_date": _parse_event_date(item) or date.today(),
                    "raw_payload": item,
                }
            )
        return events

    def search_market_context(
        self,
        *,
        query: str,
        days: int = 30,
        max_results: int = 8,
        topic: str = "news",
    ) -> list[dict[str, Any]]:
        if not self.api_key:
            return []
        payload = {
            "api_key": self.api_key,
            "query": query,
            "search_depth": "advanced",
            "topic": topic,
            "days": days,
            "max_results": max_results,
            "include_answer": False,
        }
        response = requests.post(self.base_url, json=payload, timeout=self.timeout_seconds)
        response.raise_for_status()
        data = response.json()
        results = []
        for item in data.get("results", []):
            if _looks_like_navigation_junk(item):
                continue
            title = _clean_headline(item.get("title"))
            if not title:
                continue
            results.append(
                {
                    "title": title,
                    "summary": _clean_snippet(item.get("content")),
                    "source_url": item.get("url"),
                    "source_name": item.get("source"),
                    "event_date": _parse_event_date(item),
                    "raw_payload": item,
                }
            )
        return results


class NullSearchProvider:
    def search_stock_news(self, *, symbol: str, company_name: str | None, days: int = 30) -> list[dict[str, Any]]:
        return []

    def search_market_context(
        self,
        *,
        query: str,
        days: int = 30,
        max_results: int = 8,
        topic: str = "news",
    ) -> list[dict[str, Any]]:
        return []


def _clean_headline(value: Any) -> str | None:
    if value is None:
        return None
    headline = " ".join(str(value).split()).strip()
    return headline or None


def _clean_snippet(value: Any) -> str | None:
    if value is None:
        return None
    snippet = " ".join(str(value).split()).strip()
    return snippet[:500] or None


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
    title_text = " ".join(
        str(value or "")
        for value in (
            item.get("title"),
        )
    ).lower()
    if symbol.lower() in title_text:
        return True
    company_tokens = [token.lower() for token in (company_name or "").replace(",", " ").split() if len(token) > 2]
    return any(token in title_text for token in company_tokens)


def _looks_like_navigation_junk(item: dict[str, Any]) -> bool:
    title = _clean_headline(item.get("title")) or ""
    title_text = title.lower()
    content_text = " ".join(str(item.get("content") or "").split()).lower()
    if title_text in GENERIC_NAV_HEADLINES:
        return True
    combined = f"{title_text} {content_text}".strip()
    if any(phrase in combined for phrase in NAVIGATION_JUNK_PHRASES):
        return True
    if len(content_text) > 250 and sum(1 for phrase in NAVIGATION_JUNK_PHRASES if phrase in content_text) >= 2:
        return True
    return False
