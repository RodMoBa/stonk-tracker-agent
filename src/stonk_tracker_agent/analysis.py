from __future__ import annotations

from collections import Counter
from decimal import Decimal
from typing import Any


def classify_event(event: dict[str, Any]) -> dict[str, Any]:
    text = f"{event.get('title', '')} {event.get('summary', '')}".lower()
    negative_terms = ["lawsuit", "miss", "downgrade", "probe", "recall", "loss", "layoff", "warning", "cuts"]
    positive_terms = ["beat", "upgrade", "partnership", "growth", "record", "approval", "launch", "raises"]
    sentiment = "neutral"
    if any(term in text for term in negative_terms):
        sentiment = "negative"
    if any(term in text for term in positive_terms):
        sentiment = "positive"
    impact = "medium" if sentiment != "neutral" else "low"
    return {**event, "sentiment": sentiment, "impact": impact}


def detect_outliers(symbol: str, snapshots: list[Any]) -> list[str]:
    if len(snapshots) < 2:
        return ["Stale or insufficient price history; collect more snapshots before judging short-term outliers."]
    latest = snapshots[0]
    previous = snapshots[1]
    if latest.close_price is None or previous.close_price in (None, Decimal("0")):
        return ["Latest or previous close price is missing."]
    change = (Decimal(latest.close_price) - Decimal(previous.close_price)) / Decimal(previous.close_price)
    findings: list[str] = []
    if abs(change) >= Decimal("0.05"):
        direction = "up" if change > 0 else "down"
        findings.append(f"{symbol} moved {direction} {change:.2%} versus the prior captured close.")
    if latest.volume and previous.volume and latest.volume >= previous.volume * 2:
        findings.append(f"{symbol} volume is at least 2x the previous captured volume.")
    return findings or ["No major short-term outlier detected from captured snapshots."]


def diversification_notes(stocks: list[Any]) -> list[str]:
    if not stocks:
        return ["Add watchlist stocks before diversification analysis can run."]
    sectors = Counter((_field(stock, "sector") or "Unknown") for stock in stocks)
    regions = Counter((_field(stock, "country_region") or "Unknown") for stock in stocks)
    notes = []
    top_sector, top_sector_count = sectors.most_common(1)[0]
    if top_sector_count > max(1, len(stocks) // 2):
        notes.append(f"Portfolio watchlist is concentrated in {top_sector}; research adjacent sectors for diversification.")
    else:
        notes.append("Sector exposure looks reasonably spread across the current watchlist.")
    if len(regions) == 1:
        notes.append(f"All watched stocks are tagged as {next(iter(regions))}; consider another region or currency exposure.")
    else:
        notes.append("Region exposure includes multiple markets.")
    return notes


def diversification_research_ideas(stocks: list[Any]) -> list[dict[str, str]]:
    sectors = {(_field(stock, "sector") or "Unknown").lower() for stock in stocks}
    regions = {(_field(stock, "country_region") or "Unknown").lower() for stock in stocks}
    ideas = [
        {"area": "Defensive sectors", "examples": "Utilities, consumer staples, telecom", "why": "Compare against growth-heavy or catalyst-dependent exposure."},
        {"area": "Healthcare", "examples": "Large-cap pharmaceuticals, medical devices, healthcare services", "why": "Research whether earnings drivers differ from technology and AI narratives."},
        {"area": "Industrials and infrastructure", "examples": "Railroads, automation, electrical equipment, infrastructure services", "why": "Investigate exposure tied to capital spending, reshoring, and infrastructure demand."},
        {"area": "Cash-flow and dividend-focused businesses", "examples": "Mature cash-generative companies; dividend-focused screens", "why": "Compare durability of cash flows against high-growth valuation sensitivity."},
        {"area": "Broad market or factor ETFs", "examples": "Broad index, value, quality, low-volatility, equal-weight screens", "why": "Benchmark concentration risk and single-company risk against diversified baskets."},
        {"area": "Fixed income or cash-like instruments", "examples": "Treasury bills, investment-grade bond funds, money-market style instruments", "why": "Research ballast, liquidity, and interest-rate sensitivity outside equities."},
        {"area": "International exposure", "examples": "Developed ex-US, Europe, Japan, emerging-market screens", "why": "Compare geographic, currency, valuation, and macro-cycle differences."},
        {"area": "Commodities and real assets", "examples": "Energy, metals, commodity producers, real-asset infrastructure", "why": "Investigate inflation, supply-chain, and commodity-cycle sensitivity."},
    ]
    if "technology" in sectors or "communication services" in sectors:
        ideas.insert(0, {"area": "Non-tech cash-flow businesses", "examples": "Insurance, logistics, consumer staples, selected financials", "why": "Stress-test whether the watchlist depends too heavily on AI/software/growth narratives."})
    if len(regions) <= 1:
        ideas.insert(0, {"area": "Non-domestic market exposure", "examples": "Europe, Japan, developed ex-US, selective emerging-market screens", "why": "Research whether currency and regional macro exposure are concentrated."})
    return ideas


def candidate_watchlist_research_ideas(stocks: list[Any]) -> list[dict[str, str]]:
    sectors = {(_field(stock, "sector") or "").lower() for stock in stocks}
    ideas = [
        {
            "ticker": "XLU",
            "name": "Utilities Select Sector SPDR ETF",
            "angle": "A utilities basket can be useful as a benchmark for defensive, regulated cash-flow exposure. Compare its volatility, rate sensitivity, and earnings drivers against a technology-heavy watchlist.",
        },
        {
            "ticker": "VDC",
            "name": "Vanguard Consumer Staples ETF",
            "angle": "Consumer staples can provide a lens into demand that is less tied to enterprise AI budgets or growth-stock sentiment. Review margin durability, pricing power, and recession sensitivity as comparison points.",
        },
        {
            "ticker": "XLV",
            "name": "Health Care Select Sector SPDR ETF",
            "angle": "Healthcare exposure can help compare different demand drivers such as demographics, regulated reimbursement, patents, and medical utilization. It is a research area for testing whether portfolio risk is too dependent on tech cycles.",
        },
        {
            "ticker": "VIS",
            "name": "Vanguard Industrials ETF",
            "angle": "Industrials can add a real-economy comparison set tied to capital spending, logistics, infrastructure, and manufacturing cycles. Use it to study whether watchlist companies share the same valuation and catalyst profile as physical-economy businesses.",
        },
        {
            "ticker": "VEA",
            "name": "Vanguard FTSE Developed Markets ETF",
            "angle": "Developed international exposure is a way to research geographic, currency, valuation, and macro-cycle differences. Compare earnings composition and currency sensitivity against the current watchlist.",
        },
        {
            "ticker": "BIL",
            "name": "SPDR Bloomberg 1-3 Month T-Bill ETF",
            "angle": "A short-term Treasury bill proxy can help frame liquidity, rate sensitivity, and cash-like opportunity costs. It is useful for research on volatility ballast rather than equity upside.",
        },
    ]
    if "technology" in sectors:
        ideas.extend(
            [
                {
                    "ticker": "JNJ",
                    "name": "Johnson & Johnson",
                    "angle": "A large healthcare business offers a comparison case with product, litigation, patent, and reimbursement risks rather than AI/software adoption risk. Review whether its revenue durability behaves differently from high-growth technology names.",
                },
                {
                    "ticker": "NEE",
                    "name": "NextEra Energy",
                    "angle": "NextEra can be studied as a utility and renewables operator with regulated cash flows, capital intensity, and rate sensitivity. Compare those risks against software/platform businesses and AI infrastructure narratives.",
                },
                {
                    "ticker": "UNP",
                    "name": "Union Pacific",
                    "angle": "Union Pacific provides an industrial rail comparison tied to freight volumes, pricing, fuel costs, and economic activity. It can help stress-test whether the watchlist is missing real-economy cyclicality and infrastructure exposure.",
                },
            ]
        )
    return ideas[:9]


def _field(item: Any, name: str) -> Any:
    if isinstance(item, dict):
        return item.get(name)
    return getattr(item, name)
