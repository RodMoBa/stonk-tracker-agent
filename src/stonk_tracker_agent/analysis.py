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


def _field(item: Any, name: str) -> Any:
    if isinstance(item, dict):
        return item.get(name)
    return getattr(item, name)
