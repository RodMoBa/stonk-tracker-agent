from __future__ import annotations

from datetime import datetime

from stonk_tracker_agent.reports import DISCLAIMER, FINAL_NOTE, render_markdown_report


def test_report_contains_research_sections_and_diversification_ideas():
    _, content = render_markdown_report(
        stocks=[
            {
                "symbol": "MSFT",
                "company_name": "Microsoft",
                "exchange": "NASDAQ",
                "sector": "Technology",
                "country_region": "United States",
                "currency": "USD",
                "priority": 1,
                "long_term_thesis": "Cloud and AI platform thesis.",
            }
        ],
        price_findings={"MSFT": ["MSFT moved up 6.00% versus the prior captured close."]},
        events={
            "MSFT": [
                {
                    "title": "Microsoft cloud growth improves",
                    "summary": "Azure growth was discussed.",
                    "source_url": "https://example.com/msft",
                    "source_name": "Example",
                    "sentiment": "positive",
                    "impact": "medium",
                }
            ]
        },
        diversification=["Portfolio watchlist is concentrated in Technology; research adjacent sectors for diversification."],
        diversification_ideas=[
            {
                "area": "European luxury comparison",
                "examples": "Consumer discretionary and premium-brand peers",
                "why": "Useful for comparing consumer demand sensitivity and regional exposure against a tech-heavy watchlist.",
            }
        ],
        watchlist_ideas=[
            {
                "ticker": "MC.PA",
                "name": "LVMH",
                "angle": "A luxury-goods leader can be researched as a non-tech global brand with different demand drivers, FX sensitivity, and margin structure.",
            }
        ],
        llm_summary=None,
        generated_at=datetime(2026, 5, 6, 12, 0),
    )

    assert DISCLAIMER in content
    assert "## Portfolio Diversification Review" in content
    assert "## Holding-by-Holding Research Notes" in content
    assert "## Diversification Research Ideas" in content
    assert "European luxury comparison" in content
    assert "### MC.PA - LVMH" in content
    assert "research idea for comparison only" not in content
    assert "## Research Action Ideas" in content
    assert "Research task only, not a trade instruction" in content
    assert FINAL_NOTE in content
