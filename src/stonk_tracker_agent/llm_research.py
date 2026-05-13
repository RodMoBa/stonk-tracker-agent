from __future__ import annotations

import json
import re
from datetime import date, datetime
from typing import Any

from langchain_openai import ChatOpenAI

from stonk_tracker_agent.analysis import build_outlier_context, classify_event, diversification_notes
from stonk_tracker_agent.config import Settings


# Centralize model construction so every research pass uses the same selected
# model and all non-LLM fallback paths can simply pass around `None`.
def build_research_llm(settings: Settings) -> ChatOpenAI | None:
    if not settings.openai_api_key:
        return None
    return ChatOpenAI(model=settings.openai_model, api_key=settings.openai_api_key, temperature=0.2)


# Event curation is the first LLM gate: turn noisy raw search results into a
# smaller set of company-specific, structured records for persistence.
def curate_events_with_llm(
    llm: Any | None,
    *,
    stock: dict[str, Any],
    raw_events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not raw_events:
        return []
    if llm is None:
        return [classify_event(event) for event in raw_events]
    candidates = [
        {
            "title": event.get("title"),
            "source_name": event.get("source_name"),
            "source_url": event.get("source_url"),
            "event_date": str(event.get("event_date") or ""),
            "body_snippet": _truncate(
                event.get("raw_payload", {}).get("content")
                or event.get("summary")
                or "",
                500,
            ),
        }
        for event in raw_events[:12]
    ]
    prompt = (
        "You are filtering noisy web search results for a stock research workflow.\n"
        "Keep only items that are materially relevant to the exact company or listed security.\n"
        "Reject site navigation text, market menus, generic category pages, video/share widgets, "
        "ticker-only labels, and unrelated macro headlines.\n"
        "Return JSON only as an array. Keep at most 6 items.\n"
        "Each item must contain: title, summary, source_url, source_name, event_date, sentiment, impact.\n"
        "Rules:\n"
        "- summary must be 1 sentence, concise, company-specific, and under 240 characters.\n"
        "- sentiment must be one of positive, neutral, negative.\n"
        "- impact must be one of low, medium, high.\n"
        "- If an item is irrelevant or junk, omit it.\n\n"
        f"Stock: {json.dumps(_stock_brief(stock), default=str)}\n"
        f"Candidate events: {json.dumps(candidates, default=str)}"
    )
    parsed = _invoke_json(llm, prompt)
    if not isinstance(parsed, list):
        return [classify_event(event) for event in raw_events]
    curated: list[dict[str, Any]] = []
    seen = set()
    for item in parsed:
        if not isinstance(item, dict):
            continue
        title = _clean_text(item.get("title"), max_length=500)
        if not title:
            continue
        dedupe_key = (title.lower(), str(item.get("source_url") or "").strip().lower())
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        curated.append(
            {
                "title": title,
                "summary": _clean_text(item.get("summary"), max_length=240),
                "source_url": _clean_text(item.get("source_url"), max_length=1000),
                "source_name": _clean_text(item.get("source_name"), max_length=255),
                "event_date": _parse_dateish(item.get("event_date")),
                "sentiment": _enum_or_default(item.get("sentiment"), {"positive", "neutral", "negative"}, "neutral"),
                "impact": _enum_or_default(item.get("impact"), {"low", "medium", "high"}, "medium"),
                "raw_payload": {"llm_curated": True},
            }
        )
    return curated


# This pass creates the high-level portfolio concentration narrative that the
# report uses before it drills into specific comparison ideas.
def synthesize_diversification_with_llm(
    llm: Any | None,
    *,
    stocks: list[Any],
    events_by_symbol: dict[str, list[dict[str, Any]]],
) -> list[str]:
    if not stocks:
        return ["Add watchlist stocks before diversification analysis can run."]
    if llm is None:
        return diversification_notes(stocks)
    prompt = (
        "You are a portfolio diversification research assistant.\n"
        "Return JSON only as an array of 4 to 6 concise bullet strings.\n"
        "Cover concentration, theme overlap, geographic/currency exposure, shared catalyst risk, and diversification research areas.\n"
        "Use research-support language only. Do not give trade instructions.\n\n"
        f"Stocks: {json.dumps([_stock_brief(stock) for stock in stocks], default=str)}\n"
        f"Recent events by symbol: {json.dumps(_event_headers_by_symbol(events_by_symbol), default=str)}"
    )
    parsed = _invoke_json(llm, prompt)
    if not isinstance(parsed, list):
        return diversification_notes(stocks)
    notes = [_clean_text(item, max_length=320) for item in parsed]
    return [note for note in notes if note] or diversification_notes(stocks)


# Run a second diversification pass with live market search results so the
# report can recommend current comparison categories and names instead of a
# fixed internal menu.
def research_diversification_options_with_llm(
    llm: Any | None,
    *,
    search_provider: Any | None,
    stocks: list[Any],
    diversification_notes_list: list[str],
    events_by_symbol: dict[str, list[dict[str, Any]]],
) -> dict[str, list[dict[str, str]]]:
    fallback = {"ideas": [], "candidates": []}
    if llm is None or search_provider is None or not stocks:
        return fallback
    queries = _build_diversification_queries(stocks, diversification_notes_list)
    search_results = []
    for query in queries:
        try:
            search_results.extend(search_provider.search_market_context(query=query, days=30, max_results=6, topic="news"))
        except Exception:
            continue
    prompt = (
        "You are a portfolio diversification research assistant.\n"
        "Use the portfolio snapshot and live web search results to propose research-oriented diversification options.\n"
        "Return JSON only as an object with two keys:\n"
        "ideas: array of 3 to 6 objects with keys area, examples, why.\n"
        "candidates: array of 3 to 8 objects with keys ticker, name, angle.\n"
        "Rules:\n"
        "- Avoid repeating the current dominant exposure.\n"
        "- Candidates can be equities, ETFs, or funds, but only include names that are clearly identifiable from the search context.\n"
        "- Keep angle to 1-2 lines and frame everything as research support, not advice.\n"
        "- Prefer concrete, current comparison ideas rather than generic textbook categories.\n\n"
        f"Stocks: {json.dumps([_stock_brief(stock, include_thesis=True) for stock in stocks], default=str)}\n"
        f"Diversification notes: {json.dumps(diversification_notes_list, default=str)}\n"
        f"Recent events by symbol: {json.dumps(_event_headers_by_symbol(events_by_symbol), default=str)}\n"
        f"Web search results: {json.dumps(search_results[:14], default=str)}"
    )
    parsed = _invoke_json(llm, prompt)
    if not isinstance(parsed, dict):
        return fallback
    ideas = []
    for item in parsed.get("ideas", []):
        if not isinstance(item, dict):
            continue
        area = _clean_text(item.get("area"), max_length=160)
        examples = _clean_text(item.get("examples"), max_length=220)
        why = _clean_text(item.get("why"), max_length=320)
        if area and examples and why:
            ideas.append({"area": area, "examples": examples, "why": why})
    candidates = []
    for item in parsed.get("candidates", []):
        if not isinstance(item, dict):
            continue
        ticker = _clean_text(item.get("ticker"), max_length=32)
        name = _clean_text(item.get("name"), max_length=180)
        angle = _clean_text(item.get("angle"), max_length=420)
        if ticker and name and angle:
            candidates.append({"ticker": ticker, "name": name, "angle": angle})
    return {"ideas": ideas, "candidates": candidates}


# Feed the model both heuristic flags and the underlying close/volume context
# so it can explain why a move matters rather than just restating the math.
def interpret_outliers_with_llm(
    llm: Any | None,
    *,
    stock: dict[str, Any],
    snapshots: list[Any],
    events: list[dict[str, Any]],
    heuristic_findings: list[str],
) -> list[str]:
    price_context = build_outlier_context(stock.get("symbol") or "", snapshots)
    if llm is None:
        return heuristic_findings or [price_context.get("message", "No major short-term outlier detected from captured snapshots.")]
    snapshot_brief = [
        {
            "date": getattr(snapshot, "snapshot_date", None),
            "close_price": str(getattr(snapshot, "close_price", "")),
            "volume": getattr(snapshot, "volume", None),
        }
        for snapshot in snapshots[:20]
    ]
    prompt = (
        "You are interpreting short-term stock outliers for research support.\n"
        "Return JSON only as an array of 1 to 3 concise strings.\n"
        "Each string should explain why the move may matter, whether more data is needed, and frame it as a research task rather than a trade signal.\n"
        "Use the full price/volume context rather than merely paraphrasing a heuristic rule.\n\n"
        f"Stock: {json.dumps(_stock_brief(stock), default=str)}\n"
        f"Heuristic findings: {json.dumps(heuristic_findings, default=str)}\n"
        f"Computed price context: {json.dumps(price_context, default=str)}\n"
        f"Recent snapshots: {json.dumps(snapshot_brief, default=str)}\n"
        f"Recent event headers: {json.dumps(_event_headers(events), default=str)}"
    )
    parsed = _invoke_json(llm, prompt)
    if not isinstance(parsed, list):
        return heuristic_findings or [price_context.get("message", "No major short-term outlier detected from captured snapshots.")]
    notes = [_clean_text(item, max_length=360) for item in parsed]
    return [note for note in notes if note] or heuristic_findings or [price_context.get("message", "No major short-term outlier detected from captured snapshots.")]


# This is the per-holding synthesis block that turns snapshots, events, and the
# stored thesis into the note sections rendered in the markdown report.
def generate_holding_note_with_llm(
    llm: Any | None,
    *,
    stock: dict[str, Any],
    snapshots: list[Any],
    events: list[dict[str, Any]],
    outlier_notes: list[str],
) -> dict[str, Any]:
    fallback = _fallback_holding_note(stock=stock, events=events)
    if llm is None:
        return fallback
    snapshot_brief = [
        {
            "date": getattr(snapshot, "snapshot_date", None),
            "close_price": str(getattr(snapshot, "close_price", "")),
            "volume": getattr(snapshot, "volume", None),
        }
        for snapshot in snapshots[:20]
    ]
    prompt = (
        "You are writing holding-level research notes for a stock watchlist report.\n"
        "Return JSON only as an object with these keys:\n"
        "thesis_summary, positive_drivers, risks, recent_event_interpretation, metrics_to_monitor, research_questions, research_actions.\n"
        "Use short strings or arrays of short strings. Keep everything non-advisory and research-oriented.\n\n"
        f"Stock: {json.dumps(_stock_brief(stock, include_thesis=True), default=str)}\n"
        f"Recent snapshots: {json.dumps(snapshot_brief, default=str)}\n"
        f"Recent events: {json.dumps(_event_headers(events), default=str)}\n"
        f"Short-term interpretation: {json.dumps(outlier_notes, default=str)}"
    )
    parsed = _invoke_json(llm, prompt)
    if not isinstance(parsed, dict):
        return fallback
    return {
        "thesis_summary": _clean_text(parsed.get("thesis_summary"), max_length=700) or fallback["thesis_summary"],
        "positive_drivers": _clean_list(parsed.get("positive_drivers"), fallback["positive_drivers"]),
        "risks": _clean_list(parsed.get("risks"), fallback["risks"]),
        "recent_event_interpretation": _clean_text(parsed.get("recent_event_interpretation"), max_length=500)
        or fallback["recent_event_interpretation"],
        "metrics_to_monitor": _clean_list(parsed.get("metrics_to_monitor"), fallback["metrics_to_monitor"]),
        "research_questions": _clean_list(parsed.get("research_questions"), fallback["research_questions"]),
        "research_actions": _clean_list(parsed.get("research_actions"), fallback["research_actions"]),
    }


# Deterministic note generation keeps the report usable when the OpenAI key is
# missing or an LLM response cannot be parsed safely.
def _fallback_holding_note(*, stock: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any]:
    thesis = stock.get("long_term_thesis") or "No thesis stored yet; research business model, fundamentals, catalysts, and risks."
    event_titles = [event.get("title") for event in events[:3] if event.get("title")]
    return {
        "thesis_summary": thesis,
        "positive_drivers": [
            "Revenue durability and segment growth quality.",
            "Balance sheet resilience and cash generation.",
            "Whether recent company-specific news supports the long-term case.",
        ],
        "risks": [
            "Valuation sensitivity and multiple compression risk.",
            "Customer concentration, competition, and execution risk.",
            "Repeated negative catalysts or thesis drift.",
        ],
        "recent_event_interpretation": (
            "Recent stored events to review include: " + "; ".join(event_titles) + "."
            if event_titles
            else "No recent stored events were found; collect more news history before drawing conclusions."
        ),
        "metrics_to_monitor": [
            "Revenue growth",
            "Free cash flow",
            "Margins",
            "Debt profile",
            "Volume and liquidity",
        ],
        "research_questions": [
            "What evidence would strengthen or weaken the thesis over the next 1-4 quarters?",
            "Are news-driven moves being confirmed by fundamentals?",
            "Is risk concentrated in the same macro or sector narrative as other holdings?",
        ],
        "research_actions": [
            "Compare this company with sector peers.",
            "Review the next earnings transcript and guidance changes.",
            "Build a catalyst calendar and track segment-level updates.",
        ],
    }


# Keep prompt payloads compact and consistent so every LLM call receives the
# same normalized stock shape.
def _stock_brief(stock: Any, *, include_thesis: bool = False) -> dict[str, Any]:
    data = {
        "symbol": _field(stock, "symbol"),
        "company_name": _field(stock, "company_name"),
        "exchange": _field(stock, "exchange"),
        "sector": _field(stock, "sector"),
        "country_region": _field(stock, "country_region"),
        "currency": _field(stock, "currency"),
        "priority": _field(stock, "priority"),
    }
    if include_thesis:
        data["long_term_thesis"] = _truncate(_field(stock, "long_term_thesis") or "", 1200)
    return data


# These search prompts are intentionally portfolio-level rather than single-name
# so Tavily returns candidate sectors, ETFs, and comparison companies.
def _build_diversification_queries(stocks: list[Any], diversification_notes_list: list[str]) -> list[str]:
    sectors = sorted({(_field(stock, "sector") or "Unknown") for stock in stocks})
    regions = sorted({(_field(stock, "country_region") or "Unknown") for stock in stocks})
    currencies = sorted({(_field(stock, "currency") or "Unknown") for stock in stocks})
    symbols = [_field(stock, "symbol") for stock in stocks[:8]]
    themes = " ".join(diversification_notes_list[:3])
    return [
        f"portfolio diversification research ideas for watchlist with sectors {', '.join(sectors)} regions {', '.join(regions)} currencies {', '.join(currencies)} latest 30 days",
        f"stocks or ETFs to compare against watchlist {' '.join(symbols)} concentration risk {themes} last 30 days",
    ]


def _event_headers(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "event_date": event.get("event_date"),
            "title": _truncate(event.get("title"), 220),
            "summary": _truncate(event.get("summary"), 260),
            "source_name": event.get("source_name"),
            "sentiment": event.get("sentiment"),
            "impact": event.get("impact"),
        }
        for event in events[:6]
    ]


def _event_headers_by_symbol(events_by_symbol: dict[str, list[dict[str, Any]]]) -> dict[str, list[dict[str, Any]]]:
    return {symbol: _event_headers(events) for symbol, events in events_by_symbol.items()}


# LLM responses are constrained to JSON so we can validate and persist them
# without trusting free-form prose formatting.
def _invoke_json(llm: Any, prompt: str) -> Any | None:
    try:
        response = llm.invoke(prompt)
    except Exception:
        return None
    content = getattr(response, "content", response)
    return _extract_json(str(content))


# Helpers below are defensive parsing/cleanup utilities for messy model output.
def _extract_json(text: str) -> Any | None:
    stripped = text.strip()
    fenced = re.search(r"```(?:json)?\s*(.+?)\s*```", stripped, flags=re.DOTALL)
    if fenced:
        stripped = fenced.group(1).strip()
    for candidate in (stripped, _first_json_span(stripped, "["), _first_json_span(stripped, "{")):
        if not candidate:
            continue
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    return None


def _first_json_span(text: str, opener: str) -> str | None:
    closer = "]" if opener == "[" else "}"
    start = text.find(opener)
    end = text.rfind(closer)
    if start == -1 or end == -1 or end <= start:
        return None
    return text[start : end + 1]


def _clean_list(value: Any, fallback: list[str]) -> list[str]:
    if not isinstance(value, list):
        return fallback
    cleaned = [_clean_text(item, max_length=240) for item in value]
    items = [item for item in cleaned if item]
    return items or fallback


def _clean_text(value: Any, *, max_length: int) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).split()).strip()
    if not text:
        return None
    return text[:max_length]


def _truncate(value: Any, max_length: int) -> str:
    return str(value or "")[:max_length]


def _enum_or_default(value: Any, allowed: set[str], default: str) -> str:
    cleaned = str(value or "").strip().lower()
    return cleaned if cleaned in allowed else default


def _parse_dateish(value: Any) -> date | None:
    if value is None or isinstance(value, date):
        return value
    text = str(value).strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            return None


def _field(item: Any, name: str) -> Any:
    if isinstance(item, dict):
        return item.get(name)
    return getattr(item, name)
