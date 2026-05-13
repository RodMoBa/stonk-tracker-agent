from __future__ import annotations

from datetime import date

from stonk_tracker_agent.llm_research import (
    curate_events_with_llm,
    generate_holding_note_with_llm,
    interpret_outliers_with_llm,
    research_diversification_options_with_llm,
)


class FakeResponse:
    def __init__(self, content: str):
        self.content = content


class FakeLLM:
    def __init__(self, responses: list[str]):
        self._responses = responses

    def invoke(self, prompt: str):
        return FakeResponse(self._responses.pop(0))


class FakeSearchProvider:
    def search_market_context(self, *, query: str, days: int = 30, max_results: int = 8, topic: str = "news"):
        return [
            {
                "title": "Healthcare and staples attract defensive interest",
                "summary": "Recent market coverage highlights healthcare and staples as non-tech comparison areas.",
                "source_url": "https://example.com/defensive",
                "source_name": "Example",
                "event_date": date(2026, 5, 2),
            }
        ]


def test_curate_events_with_llm_keeps_only_relevant_items():
    llm = FakeLLM(
        [
            """
            ```json
            [
              {
                "title": "Microsoft cloud growth improves after enterprise demand uptick",
                "summary": "Enterprise cloud demand supports the company-specific growth narrative.",
                "source_url": "https://example.com/msft",
                "source_name": "Example",
                "event_date": "2026-05-01",
                "sentiment": "positive",
                "impact": "medium"
              }
            ]
            ```
            """
        ]
    )

    curated = curate_events_with_llm(
        llm,
        stock={"symbol": "MSFT", "company_name": "Microsoft"},
        raw_events=[
            {
                "title": "Microsoft cloud growth improves after enterprise demand uptick",
                "summary": None,
                "source_url": "https://example.com/msft",
                "source_name": "Example",
                "event_date": date(2026, 5, 1),
                "raw_payload": {"content": "Longer article body."},
            }
        ],
    )

    assert len(curated) == 1
    assert curated[0]["title"].startswith("Microsoft cloud growth improves")
    assert curated[0]["summary"] == "Enterprise cloud demand supports the company-specific growth narrative."
    assert curated[0]["sentiment"] == "positive"


def test_generate_holding_note_with_llm_parses_structured_json():
    llm = FakeLLM(
        [
            """
            {
              "thesis_summary": "Microsoft remains a cloud and productivity platform research candidate with AI monetization upside.",
              "positive_drivers": ["Recurring enterprise revenue", "AI product cross-sell"],
              "risks": ["Cloud budget pressure", "Valuation sensitivity"],
              "recent_event_interpretation": "Recent company-specific headlines appear supportive but still need confirmation in fundamentals.",
              "metrics_to_monitor": ["Azure growth", "Operating margin", "Free cash flow"],
              "research_questions": ["Is AI monetization incremental or substitutive?"],
              "research_actions": ["Review the next earnings transcript for segment commentary."]
            }
            """
        ]
    )

    note = generate_holding_note_with_llm(
        llm,
        stock={"symbol": "MSFT", "company_name": "Microsoft", "long_term_thesis": "Cloud thesis."},
        snapshots=[],
        events=[],
        outlier_notes=["A recent move warrants more catalyst review."],
    )

    assert "cloud and productivity" in note["thesis_summary"].lower()
    assert note["positive_drivers"] == ["Recurring enterprise revenue", "AI product cross-sell"]
    assert note["risks"] == ["Cloud budget pressure", "Valuation sensitivity"]


def test_research_diversification_options_with_llm_returns_structured_ideas():
    llm = FakeLLM(
        [
            """
            {
              "ideas": [
                {
                  "area": "Healthcare cash-flow comparison",
                  "examples": "Large-cap pharma and diversified healthcare funds",
                  "why": "This helps compare different demand drivers and regulatory exposure against a tech-heavy watchlist."
                }
              ],
              "candidates": [
                {
                  "ticker": "XLV",
                  "name": "Health Care Select Sector SPDR Fund",
                  "angle": "A liquid healthcare basket can be researched as a contrast to software and AI concentration risk."
                }
              ]
            }
            """
        ]
    )

    result = research_diversification_options_with_llm(
        llm,
        search_provider=FakeSearchProvider(),
        stocks=[{"symbol": "MSFT", "sector": "Technology", "country_region": "United States", "currency": "USD"}],
        diversification_notes_list=["Portfolio watchlist is concentrated in Technology; research adjacent sectors for diversification."],
        events_by_symbol={},
    )

    assert result["ideas"][0]["area"] == "Healthcare cash-flow comparison"
    assert result["candidates"][0]["ticker"] == "XLV"


def test_interpret_outliers_with_llm_uses_context_without_heuristic_findings():
    llm = FakeLLM(
        [
            """
            [
              "The recent close and volume pattern does not show a clear one-day shock, so more observations are needed before treating it as a meaningful outlier. This is a research task, not a trade signal."
            ]
            """
        ]
    )

    class Snapshot:
        def __init__(self, snapshot_date, close_price, volume):
            self.snapshot_date = snapshot_date
            self.close_price = close_price
            self.volume = volume

    notes = interpret_outliers_with_llm(
        llm,
        stock={"symbol": "MSFT", "company_name": "Microsoft"},
        snapshots=[
            Snapshot(date(2026, 5, 5), "100", 1000),
            Snapshot(date(2026, 5, 4), "99", 1100),
            Snapshot(date(2026, 5, 3), "101", 950),
        ],
        events=[],
        heuristic_findings=[],
    )

    assert len(notes) == 1
    assert "research task" in notes[0].lower()
