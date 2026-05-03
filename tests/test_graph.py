from __future__ import annotations

from datetime import date

from stonk_tracker_agent.graph import build_report_graph
from stonk_tracker_agent.config import Settings
from stonk_tracker_agent.db.repositories import ResearchRepository, WatchlistRepository


class FakeMarketProvider:
    def get_snapshot(self, symbol: str):
        return {
            "snapshot_date": date(2026, 5, 1),
            "open_price": "100",
            "high_price": "110",
            "low_price": "99",
            "close_price": "108",
            "volume": 2000,
            "raw_payload": {"symbol": symbol},
        }


class FakeSearchProvider:
    def search_stock_news(self, *, symbol: str, company_name: str | None, days: int = 7):
        return [
            {
                "title": f"{symbol} launches new product",
                "summary": "Growth story improves after launch.",
                "source_url": "https://example.com/story",
                "source_name": "Example",
                "event_date": date(2026, 5, 1),
            }
        ]


def test_report_graph_persists_report(session, tmp_path):
    WatchlistRepository(session).upsert(symbol="MSFT", exchange="NASDAQ", sector="Technology", country_region="US")
    settings = Settings(database_url="sqlite://", reports_dir=tmp_path)
    graph = build_report_graph(
        session,
        settings=settings,
        market_provider=FakeMarketProvider(),
        search_provider=FakeSearchProvider(),
    )

    result = graph.invoke(
        {"run_started_at": date(2026, 5, 1), "messages": []},
        config={"configurable": {"thread_id": "test-run"}},
    )

    reports = ResearchRepository(session).list_reports()
    assert len(reports) == 1
    assert result["report_path"]

