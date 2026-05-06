from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from langchain_openai import ChatOpenAI
from sqlalchemy.orm import Session

from stonk_tracker_agent.analysis import classify_event
from stonk_tracker_agent.config import Settings, get_settings
from stonk_tracker_agent.db.models import WatchlistStock
from stonk_tracker_agent.db.repositories import ResearchRepository, WatchlistRepository
from stonk_tracker_agent.providers.market import YFinanceMarketDataProvider
from stonk_tracker_agent.providers.search import NullSearchProvider, TavilySearchProvider


@dataclass
class WatchlistEnrichmentResult:
    stock: WatchlistStock
    events_saved: int
    prices_saved: int
    thesis: str
    profile: dict[str, Any]


def enrich_and_save_stock(
    session: Session,
    *,
    symbol: str,
    preferred_currency: str,
    priority: int,
    active: bool,
    company_name: str | None = None,
    manual_notes: str | None = None,
    settings: Settings | None = None,
    market_provider: Any | None = None,
    search_provider: Any | None = None,
) -> WatchlistEnrichmentResult:
    settings = settings or get_settings()
    market_provider = market_provider or YFinanceMarketDataProvider()
    search_provider = search_provider or (TavilySearchProvider(settings.tavily_api_key) if settings.tavily_api_key else NullSearchProvider())
    watchlist_repo = WatchlistRepository(session)
    research_repo = ResearchRepository(session)

    normalized_symbol = symbol.strip().upper()
    try:
        profile = market_provider.get_profile(normalized_symbol)
    except Exception:
        profile = {"symbol": normalized_symbol}
    resolved_company = company_name or profile.get("company_name") or normalized_symbol
    resolved_currency = preferred_currency or profile.get("currency")

    stock = watchlist_repo.upsert(
        symbol=normalized_symbol,
        exchange=profile.get("exchange"),
        country_region=profile.get("country_region"),
        currency=resolved_currency,
        company_name=resolved_company,
        sector=profile.get("sector"),
        priority=priority,
        long_term_thesis=manual_notes,
        active=active,
    )

    profile_event = _profile_event(normalized_symbol, profile)
    saved_events = 0
    if profile_event:
        research_repo.save_event(stock, profile_event)
        saved_events += 1

    try:
        raw_events = search_provider.search_stock_news(symbol=normalized_symbol, company_name=resolved_company, days=30)
    except Exception:
        raw_events = []
    classified_events = [classify_event(event) for event in raw_events]
    for event in classified_events:
        research_repo.save_event(stock, event)
        saved_events += 1

    try:
        price_history = market_provider.get_history(normalized_symbol, days=90)
    except Exception:
        price_history = []
    prices_saved = research_repo.save_price_history(stock, price_history) if price_history else 0
    thesis = generate_long_term_thesis(
        settings=settings,
        symbol=normalized_symbol,
        profile=profile,
        events=classified_events,
        manual_notes=manual_notes,
    )

    stock = watchlist_repo.upsert(
        symbol=normalized_symbol,
        exchange=profile.get("exchange"),
        country_region=profile.get("country_region"),
        currency=resolved_currency,
        company_name=resolved_company,
        sector=profile.get("sector"),
        priority=priority,
        long_term_thesis=thesis,
        active=active,
    )
    return WatchlistEnrichmentResult(
        stock=stock,
        events_saved=saved_events,
        prices_saved=prices_saved,
        thesis=thesis,
        profile=profile,
    )


def generate_long_term_thesis(
    *,
    settings: Settings,
    symbol: str,
    profile: dict[str, Any],
    events: list[dict[str, Any]],
    manual_notes: str | None,
) -> str:
    fallback = _fallback_thesis(symbol=symbol, profile=profile, events=events, manual_notes=manual_notes)
    if not settings.openai_api_key:
        return fallback
    llm = ChatOpenAI(model=settings.openai_model, api_key=settings.openai_api_key, temperature=0.2)
    prompt = (
        "Generate a concise long-term investment research thesis for a stock watchlist. "
        "Use evidence only from the profile and news events below. "
        "Do not give direct buy/sell instructions. Include durable strengths, risks, and what to monitor.\n\n"
        f"Symbol: {symbol}\n"
        f"Profile: {profile}\n"
        f"Recent events: {events[:10]}\n"
        f"User notes: {manual_notes or ''}"
    )
    try:
        response = llm.invoke(prompt)
    except Exception:
        return fallback
    return str(response.content) or fallback


def _fallback_thesis(*, symbol: str, profile: dict[str, Any], events: list[dict[str, Any]], manual_notes: str | None) -> str:
    company = profile.get("company_name") or symbol
    sector = profile.get("sector") or "an unknown sector"
    country = profile.get("country_region") or "an unknown region"
    summary = profile.get("long_business_summary")
    event_titles = [event.get("title") for event in events[:3] if event.get("title")]
    parts = [
        f"{company} ({symbol}) is tracked as a long-term watchlist candidate in {sector}, based in {country}.",
    ]
    if summary:
        parts.append(str(summary)[:1200])
    if event_titles:
        parts.append("Recent research items to monitor: " + "; ".join(event_titles) + ".")
    if manual_notes:
        parts.append("User notes: " + manual_notes)
    parts.append("Monitor fundamentals, competitive position, valuation, repeated negative catalysts, and whether recent news supports the long-term thesis.")
    return "\n\n".join(parts)


def _profile_event(symbol: str, profile: dict[str, Any]) -> dict[str, Any] | None:
    company = profile.get("company_name")
    if not company:
        return None
    resolved_symbol = profile.get("resolved_symbol") or symbol
    summary_parts = [
        f"Company profile resolved from Yahoo Finance as {resolved_symbol}.",
        f"Exchange: {profile.get('exchange') or 'unknown'}.",
        f"Country/region: {profile.get('country_region') or 'unknown'}.",
        f"Currency: {profile.get('currency') or 'unknown'}.",
        f"Sector: {profile.get('sector') or 'unknown'}.",
    ]
    if profile.get("industry"):
        summary_parts.append(f"Industry: {profile['industry']}.")
    if profile.get("long_business_summary"):
        summary_parts.append(str(profile["long_business_summary"])[:1500])
    return {
        "title": f"Company profile snapshot: {company}",
        "summary": " ".join(summary_parts),
        "source_url": f"https://finance.yahoo.com/quote/{resolved_symbol}",
        "source_name": "Yahoo Finance",
        "sentiment": "neutral",
        "impact": "low",
        "raw_payload": {"provider": "yfinance", "profile": profile},
    }
