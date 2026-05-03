from __future__ import annotations

from stonk_tracker_agent.providers.market import NullMarketDataProvider
from stonk_tracker_agent.providers.search import NullSearchProvider


def test_null_market_provider_returns_no_snapshot():
    assert NullMarketDataProvider().get_snapshot("MSFT") is None


def test_null_search_provider_returns_no_events():
    assert NullSearchProvider().search_stock_news(symbol="MSFT", company_name="Microsoft") == []

