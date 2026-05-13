from __future__ import annotations

from datetime import date

from stonk_tracker_agent.config import Settings
from stonk_tracker_agent.db.repositories import ResearchRepository, WatchlistRepository
from stonk_tracker_agent.focused_research import generate_focused_stock_report


class FakeResponsesAPI:
    def create(self, **kwargs):
        return FakeOpenAIResponse(
            output_text=(
                "## Disclaimer\n\n"
                "Research support only.\n\n"
                "## Web Research Findings\n\n"
                "Recent reporting highlighted product momentum and analyst focus on cloud demand."
            ),
            output=[
                FakeWebSearchCall(
                    FakeActionSearch(
                        queries=["Microsoft recent earnings news", "Microsoft cloud demand latest"],
                        sources=[
                            FakeSource("Microsoft earnings recap", "https://example.com/earnings"),
                            FakeSource("Cloud demand update", "https://example.com/cloud"),
                        ],
                    )
                )
            ],
        )


class FakeOpenAIClient:
    def __init__(self):
        self.responses = FakeResponsesAPI()


class FakeOpenAIResponse:
    def __init__(self, *, output_text: str, output: list[dict]):
        self.output_text = output_text
        self.output = output


class FakeWebSearchCall:
    type = "web_search_call"

    def __init__(self, action):
        self.action = action


class FakeActionSearch:
    def __init__(self, *, queries: list[str], sources: list[object]):
        self.queries = queries
        self.sources = sources


class FakeSource:
    def __init__(self, title: str, url: str):
        self.title = title
        self.url = url


def test_generate_focused_stock_report_uses_openai_web_search_and_saves_report(session, tmp_path):
    stock = WatchlistRepository(session).upsert(
        symbol="MSFT",
        exchange="NASDAQ",
        company_name="Microsoft",
        sector="Technology",
        country_region="United States",
        currency="USD",
    )
    repo = ResearchRepository(session)
    repo.save_price_history(
        stock,
        [
            {
                "snapshot_date": date(2026, 5, 1),
                "open_price": 100,
                "high_price": 105,
                "low_price": 99,
                "close_price": 103,
                "volume": 1000,
                "raw_payload": {"symbol": "MSFT"},
            },
            {
                "snapshot_date": date(2026, 5, 2),
                "open_price": 103,
                "high_price": 110,
                "low_price": 102,
                "close_price": 108,
                "volume": 1800,
                "raw_payload": {"symbol": "MSFT"},
            },
        ],
    )
    repo.save_event(
        stock,
        {
            "event_date": date(2026, 5, 2),
            "title": "Microsoft cloud growth improves",
            "summary": "Stored event summary.",
            "source_url": "https://example.com/msft-event",
            "source_name": "Example",
            "sentiment": "positive",
            "impact": "medium",
        },
    )

    result = generate_focused_stock_report(
        session,
        stock_id=stock.id,
        model="gpt-5.5",
        settings=Settings(openai_api_key="test-key", reports_dir=tmp_path),
        openai_client=FakeOpenAIClient(),
    )

    assert result.web_search_used is True
    assert result.web_queries == ["Microsoft recent earnings news", "Microsoft cloud demand latest"]
    assert len(result.web_sources) == 2
    assert len(result.chart_paths) == 2
    assert all(path.exists() for path in result.chart_paths)
    assert result.pdf_bytes.startswith(b"%PDF")
    assert result.markdown_path.exists()
    assert "Web Search Trace" in result.markdown
    assert "![Msft Close Price]" in result.markdown
