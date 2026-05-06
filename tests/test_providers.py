from __future__ import annotations

from stonk_tracker_agent.providers.market import NullMarketDataProvider, yahoo_symbol_candidates
from stonk_tracker_agent.providers.search import NullSearchProvider


def test_null_market_provider_returns_no_snapshot():
    assert NullMarketDataProvider().get_history("MSFT") == []


def test_null_search_provider_returns_no_events():
    assert NullSearchProvider().search_stock_news(symbol="MSFT", company_name="Microsoft") == []


def test_yahoo_symbol_candidates_try_frankfurt_suffix_for_bare_symbols():
    candidates = yahoo_symbol_candidates("48ca")

    assert candidates[0] == "48CA"
    assert "48CA.F" in candidates


def test_yahoo_symbol_candidates_do_not_expand_explicit_suffix():
    assert yahoo_symbol_candidates("48CA.F") == ["48CA.F"]
