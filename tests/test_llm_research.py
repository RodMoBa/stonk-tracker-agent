from __future__ import annotations

from datetime import date

from stonk_tracker_agent.llm_research import curate_events_with_llm, generate_holding_note_with_llm


class FakeResponse:
    def __init__(self, content: str):
        self.content = content


class FakeLLM:
    def __init__(self, responses: list[str]):
        self._responses = responses

    def invoke(self, prompt: str):
        return FakeResponse(self._responses.pop(0))


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
