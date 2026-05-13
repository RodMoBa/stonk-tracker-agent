from __future__ import annotations

from datetime import date

from stonk_tracker_agent.config import Settings
from stonk_tracker_agent.db.repositories import ResearchRepository
from stonk_tracker_agent.watchlist_enrichment import enrich_and_save_stock


class FakeMarketProvider:
    def get_profile(self, symbol: str):
        return {
            "symbol": symbol,
            "exchange": "NASDAQ",
            "country_region": "United States",
            "currency": "USD",
            "company_name": "Microsoft Corporation",
            "sector": "Technology",
            "long_business_summary": "Microsoft builds cloud, productivity, and AI platforms.",
        }

    def get_history(self, symbol: str, days: int = 90):
        return [
            {
                "snapshot_date": date(2026, 5, 1),
                "open_price": 100,
                "high_price": 110,
                "low_price": 99,
                "close_price": 108,
                "volume": 2000,
                "raw_payload": {"symbol": symbol},
            }
        ]


class FakeSearchProvider:
    def search_stock_news(self, *, symbol: str, company_name: str | None, days: int = 30):
        return [
            {
                "event_date": date(2026, 5, 1),
                "title": "Microsoft cloud growth improves",
                "summary": None,
                "source_url": "https://example.com/msft-cloud",
                "source_name": "Example",
            }
        ]


def test_enrich_and_save_stock_generates_profile_thesis_news_and_prices(session):
    result = enrich_and_save_stock(
        session,
        symbol="msft",
        preferred_currency="USD",
        priority=2,
        active=True,
        settings=Settings(openai_api_key=None),
        market_provider=FakeMarketProvider(),
        search_provider=FakeSearchProvider(),
    )

    repo = ResearchRepository(session)
    assert result.stock.symbol == "MSFT"
    assert result.stock.exchange == "NASDAQ"
    assert result.stock.country_region == "United States"
    assert result.stock.sector == "Technology"
    assert result.stock.currency == "USD"
    assert "Microsoft Corporation" in result.stock.long_term_thesis
    assert result.events_saved == 2
    assert result.prices_saved == 1
    assert len(repo.recent_events(result.stock.id)) == 2
    assert len(repo.recent_snapshots(result.stock.id)) == 1
