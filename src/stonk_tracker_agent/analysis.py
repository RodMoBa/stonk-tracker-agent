from __future__ import annotations

from collections import Counter
from decimal import Decimal
from typing import Any


# Lightweight keyword scoring is the deterministic fallback when GPT curation
# is unavailable during event ingestion.
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


# Surface obvious moves quickly, then let the LLM decide how to interpret the
# richer context for the report.
def detect_outliers(symbol: str, snapshots: list[Any]) -> list[str]:
    context = build_outlier_context(symbol, snapshots)
    if context["status"] != "ok":
        return [context["message"]]
    findings: list[str] = []
    change = context["latest_change_1d"]
    if change is not None and abs(change) >= Decimal("0.05"):
        direction = "up" if change > 0 else "down"
        findings.append(f"{symbol} moved {direction} {change:.2%} versus the prior captured close.")
    if context["volume_ratio_1d"] is not None and context["volume_ratio_1d"] >= Decimal("2"):
        findings.append(f"{symbol} volume is at least 2x the previous captured volume.")
    if context["change_5d"] is not None and abs(context["change_5d"]) >= Decimal("0.10"):
        direction = "up" if context["change_5d"] > 0 else "down"
        findings.append(f"{symbol} moved {direction} {context['change_5d']:.2%} over the last 5 captured closes.")
    return findings or ["No major short-term outlier detected from captured snapshots."]


# Package the recent close and volume history into a structured summary so the
# LLM can reason over real stored pricing context rather than a single formula.
def build_outlier_context(symbol: str, snapshots: list[Any]) -> dict[str, Any]:
    if len(snapshots) < 2:
        return {
            "symbol": symbol,
            "status": "insufficient",
            "message": "Stale or insufficient price history; collect more snapshots before judging short-term outliers.",
        }
    latest = snapshots[0]
    previous = snapshots[1]
    if latest.close_price is None or previous.close_price in (None, Decimal("0")):
        return {
            "symbol": symbol,
            "status": "missing_prices",
            "message": "Latest or previous close price is missing.",
        }
    closes = [Decimal(snapshot.close_price) for snapshot in snapshots if getattr(snapshot, "close_price", None) not in (None, "")]
    volumes = [snapshot.volume for snapshot in snapshots if getattr(snapshot, "volume", None) is not None]
    latest_change_1d = _pct_change(Decimal(latest.close_price), Decimal(previous.close_price))
    volume_ratio_1d = None
    if latest.volume and previous.volume:
        volume_ratio_1d = Decimal(str(latest.volume)) / Decimal(str(previous.volume))
    return {
        "symbol": symbol,
        "status": "ok",
        "latest_snapshot_date": getattr(latest, "snapshot_date", None),
        "latest_close": Decimal(latest.close_price),
        "previous_close": Decimal(previous.close_price),
        "latest_change_1d": latest_change_1d,
        "change_5d": _window_change(closes, 5),
        "change_20d": _window_change(closes, 20),
        "close_range_20d": _range_ratio(closes[:20]),
        "average_volume_5d": _average(volumes[:5]),
        "average_volume_20d": _average(volumes[:20]),
        "latest_volume": latest.volume,
        "volume_ratio_1d": volume_ratio_1d,
        "recent_closes": [str(close) for close in closes[:20]],
        "recent_volumes": volumes[:20],
    }


# These notes remain as deterministic fallbacks when live search or GPT-based
# diversification synthesis is unavailable.
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


# Keep a minimal non-static fallback shape for the report table; the normal path
# now comes from live search plus GPT synthesis in llm_research.py.
def diversification_research_ideas(stocks: list[Any]) -> list[dict[str, str]]:
    notes = diversification_notes(stocks)
    areas = []
    if any("concentrated in" in note.lower() for note in notes):
        areas.append(
            {
                "area": "Adjacent sectors",
                "examples": "Industrials, healthcare, consumer staples, utilities, selected financials",
                "why": "Useful when a watchlist appears concentrated in one dominant sector or growth narrative.",
            }
        )
    if any("currency exposure" in note.lower() or "region" in note.lower() for note in notes):
        areas.append(
            {
                "area": "International exposure",
                "examples": "Developed ex-US, Europe, Japan, broad international ETFs, country-specific leaders",
                "why": "Helps compare valuation, policy, and macro-cycle differences outside the existing region mix.",
            }
        )
    areas.append(
        {
            "area": "Cash-flow resilience",
            "examples": "Defensive sectors, mature compounders, income-oriented funds, infrastructure",
            "why": "Useful for comparing steadier cash generation against more cyclical or narrative-driven holdings.",
        }
    )
    return areas


# The renderer expects some comparison block even when dynamic research fails,
# so this fallback is intentionally generic.
def candidate_watchlist_research_ideas(stocks: list[Any]) -> list[dict[str, str]]:
    sectors = {(_field(stock, "sector") or "").lower() for stock in stocks}
    primary_sector = sorted(sectors)[0] if sectors else "current exposure"
    return [
        {
            "ticker": "TBD",
            "name": "Dynamic research candidate",
            "angle": f"Use live search and model synthesis to find comparison names outside {primary_sector} concentration rather than relying on a fixed internal list.",
        }
    ]


# Small helpers below keep the outlier-context math readable inside the main
# function above.
def _pct_change(current: Decimal, previous: Decimal) -> Decimal | None:
    if previous == 0:
        return None
    return (current - previous) / previous


def _window_change(closes: list[Decimal], window: int) -> Decimal | None:
    if len(closes) < window:
        return None
    current = closes[0]
    baseline = closes[window - 1]
    return _pct_change(current, baseline)


def _average(values: list[Any]) -> Decimal | None:
    cleaned = [Decimal(str(value)) for value in values if value not in (None, "")]
    if not cleaned:
        return None
    return sum(cleaned) / Decimal(len(cleaned))


def _range_ratio(closes: list[Decimal]) -> Decimal | None:
    if len(closes) < 2:
        return None
    low = min(closes)
    high = max(closes)
    if low == 0:
        return None
    return (high - low) / low


def _field(item: Any, name: str) -> Any:
    if isinstance(item, dict):
        return item.get(name)
    return getattr(item, name)
