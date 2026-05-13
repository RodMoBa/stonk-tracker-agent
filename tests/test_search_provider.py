from __future__ import annotations

from datetime import date

from stonk_tracker_agent.providers.search import TavilySearchProvider, _is_relevant_result, _looks_like_navigation_junk


def test_relevance_filter_accepts_symbol_or_company_name():
    assert _is_relevant_result({"title": "MSFT rises after earnings"}, symbol="MSFT", company_name="Microsoft")
    assert _is_relevant_result({"title": "Microsoft Azure growth accelerates"}, symbol="MSFT", company_name="Microsoft")


def test_relevance_filter_rejects_unrelated_news():
    assert not _is_relevant_result({"title": "Waters announces FDA clearance"}, symbol="MSFT", company_name="Microsoft")


def test_tavily_provider_keeps_only_headline_summary_free_events(mocker):
    provider = TavilySearchProvider("test-key")
    mock_response = mocker.Mock()
    mock_response.json.return_value = {
        "results": [
            {
                "title": "  Microsoft   cloud growth improves  ",
                "content": "Long noisy body text that should not be persisted.",
                "url": "https://example.com/msft",
                "source": "Example",
                "published_date": "2026-05-01",
            }
        ]
    }
    mock_response.raise_for_status.return_value = None
    post = mocker.patch("stonk_tracker_agent.providers.search.requests.post", return_value=mock_response)

    events = provider.search_stock_news(symbol="MSFT", company_name="Microsoft", days=30)

    assert len(events) == 1
    assert events[0]["title"] == "Microsoft cloud growth improves"
    assert events[0]["summary"] is None
    assert events[0]["event_date"] == date(2026, 5, 1)
    assert "headlines" in post.call_args.kwargs["json"]["query"]


def test_navigation_junk_is_rejected():
    assert _looks_like_navigation_junk(
        {
            "title": "MC.PA",
            "content": "Skip Navigation Markets Pre-Markets U.S. Markets Europe Markets Asia Markets Video watch now Share",
        }
    )
