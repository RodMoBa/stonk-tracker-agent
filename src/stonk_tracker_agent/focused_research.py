from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from openai import OpenAI
from sqlalchemy.orm import Session

from stonk_tracker_agent.analysis import build_outlier_context
from stonk_tracker_agent.config import Settings, get_settings
from stonk_tracker_agent.db.models import WatchlistStock
from stonk_tracker_agent.db.repositories import ResearchRepository
from stonk_tracker_agent.reports import render_pdf_report, save_markdown_report


@dataclass
class FocusedResearchResult:
    title: str
    markdown: str
    markdown_path: Path
    pdf_bytes: bytes
    web_search_used: bool
    web_queries: list[str]
    web_sources: list[dict[str, str]]
    model: str
    stock_symbol: str
    chart_paths: list[Path]


# This path is intentionally separate from the portfolio report graph: it is a
# single-stock deep dive that explicitly uses OpenAI web search and combines it
# with locally stored price and event history.
def generate_focused_stock_report(
    session: Session,
    *,
    stock_id: int,
    model: str,
    settings: Settings | None = None,
    openai_client: Any | None = None,
) -> FocusedResearchResult:
    settings = settings or get_settings()
    if not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY is not configured.")
    stock = session.get(WatchlistStock, stock_id)
    if stock is None:
        raise ValueError(f"Unknown stock id: {stock_id}")

    research_repo = ResearchRepository(session)
    snapshots = list(reversed(research_repo.recent_snapshots(stock.id, limit=60)))
    recent_events = list(reversed(research_repo.recent_events(stock.id, limit=20)))
    report_started_at = utc_now()

    openai_client = openai_client or OpenAI(api_key=settings.openai_api_key)
    prompt = _build_focused_prompt(stock=stock, snapshots=snapshots, events=recent_events)
    response = _run_openai_web_research(openai_client, model=model, prompt=prompt)
    output_text = _response_output_text(response)
    web_queries = _extract_web_queries(response)
    web_sources = _extract_web_sources(response)
    title = f"Focused Stock Research - {stock.symbol} - {report_started_at:%Y-%m-%d %H:%M}"
    chart_paths = _create_focused_chart_assets(stock=stock, snapshots=snapshots, reports_dir=settings.reports_dir, generated_at=report_started_at)
    markdown = _assemble_focused_markdown(
        stock=stock,
        model=model,
        body=output_text,
        web_queries=web_queries,
        web_sources=web_sources,
        snapshots=snapshots,
        events=recent_events,
        chart_paths=chart_paths,
    )
    markdown_path = save_markdown_report(settings.reports_dir, title, markdown, report_started_at)
    research_repo.save_report(
        title=title,
        markdown_path=markdown_path,
        symbols_covered=[stock.symbol],
        run_started_at=report_started_at,
        run_finished_at=utc_now(),
        summary=output_text[:1200],
    )
    return FocusedResearchResult(
        title=title,
        markdown=markdown,
        markdown_path=markdown_path,
        pdf_bytes=render_pdf_report(markdown, title=title),
        web_search_used=bool(web_queries or web_sources or _response_has_web_search(response)),
        web_queries=web_queries,
        web_sources=web_sources,
        model=model,
        stock_symbol=stock.symbol,
        chart_paths=chart_paths,
    )


def _run_openai_web_research(openai_client: Any, *, model: str, prompt: str) -> Any:
    # First try to force a web search tool call so the focused screen can show
    # explicit evidence that web search was used during synthesis.
    try:
        return openai_client.responses.create(
            model=model,
            tools=[
                {
                    "type": "web_search",
                    "user_location": {"type": "approximate", "country": "ES", "timezone": "Europe/Madrid"},
                }
            ],
            tool_choice={"type": "web_search"},
            include=["web_search_call.action.sources"],
            input=prompt,
        )
    except Exception:
        # Some models or SDK versions may reject forced tool selection, so fall
        # back to auto while keeping the prompt explicit about mandatory search.
        return openai_client.responses.create(
            model=model,
            tools=[
                {
                    "type": "web_search",
                    "user_location": {"type": "approximate", "country": "ES", "timezone": "Europe/Madrid"},
                }
            ],
            tool_choice="auto",
            include=["web_search_call.action.sources"],
            input=prompt,
        )


def _build_focused_prompt(*, stock: WatchlistStock, snapshots: list[Any], events: list[Any]) -> str:
    event_context = [
        {
            "date": event.event_date.isoformat() if event.event_date else None,
            "title": event.title,
            "summary": event.summary,
            "source_name": event.source_name,
            "source_url": event.source_url,
            "sentiment": event.sentiment,
            "impact": event.impact,
        }
        for event in events
    ]
    price_context = [
        {
            "date": snapshot.snapshot_date.isoformat(),
            "open": _decimal_str(snapshot.open_price),
            "high": _decimal_str(snapshot.high_price),
            "low": _decimal_str(snapshot.low_price),
            "close": _decimal_str(snapshot.close_price),
            "volume": snapshot.volume,
        }
        for snapshot in snapshots
    ]
    outlier_context = build_outlier_context(stock.symbol, list(reversed(snapshots)))
    return (
        "You are a focused single-stock research assistant.\n"
        "You must perform web searches before answering. Use web search explicitly for:\n"
        "1. recent company news and catalysts\n"
        "2. earnings, guidance, or analyst context\n"
        "3. competitive or sector context\n"
        "4. any macro or regulatory issue materially linked to this stock\n\n"
        "You are also given internal database context from the local system. Use both the web search results and the provided database data.\n"
        "Do not give financial advice or trading instructions.\n"
        "Write a markdown report with these sections:\n"
        "## Disclaimer\n"
        "## Company Snapshot\n"
        "## Database Price and Volume Read\n"
        "## Stored News and Catalyst History\n"
        "## Web Research Findings\n"
        "## Short-Term Outlier Interpretation\n"
        "## Long-Term Thesis Stress Test\n"
        "## Focused Follow-Up Questions\n"
        "## Final Note\n\n"
        "Be explicit about how the stored database context and the web research agree or disagree.\n\n"
        f"Stock metadata: {stock.symbol}, {stock.company_name}, exchange={stock.exchange}, sector={stock.sector}, region={stock.country_region}, currency={stock.currency}, priority={stock.priority}\n"
        f"Stored long-term thesis: {stock.long_term_thesis or 'None'}\n"
        f"Stored price history context: {price_context}\n"
        f"Stored outlier context: {outlier_context}\n"
        f"Stored events/news context: {event_context}"
    )


def _assemble_focused_markdown(
    *,
    stock: WatchlistStock,
    model: str,
    body: str,
    web_queries: list[str],
    web_sources: list[dict[str, str]],
    snapshots: list[Any],
    events: list[Any],
    chart_paths: list[Path],
) -> str:
    lines = [
        f"# Focused Stock Research - {stock.symbol}",
        "",
        f"Model used: `{model}`",
        "",
        body.strip(),
        "",
        "## Web Search Trace",
        "",
        f"- Web search invoked: {'yes' if web_queries or web_sources else 'not observed in parsed response'}",
    ]
    if chart_paths:
        lines.extend(["", "## Visual Snapshot", ""])
        for chart_path in chart_paths:
            label = chart_path.stem.replace("-", " ").title()
            lines.append(f"![{label}]({chart_path.as_posix()})")
    if web_queries:
        lines.append("- Search queries used:")
        lines.extend(f"  - {query}" for query in web_queries)
    if web_sources:
        lines.extend(["", "## Web Sources", ""])
        for source in web_sources:
            label = source.get("title") or source.get("url") or "source"
            url = source.get("url")
            if url:
                lines.append(f"- [{label}]({url})")
            else:
                lines.append(f"- {label}")
    if snapshots:
        lines.extend(["", "## Stored Price Snapshot Count", "", f"- {len(snapshots)} rows used from the database."])
    if events:
        lines.extend(["", "## Stored Event Count", "", f"- {len(events)} stored event rows used from the database."])
    return "\n".join(lines).strip() + "\n"


def _response_output_text(response: Any) -> str:
    output_text = getattr(response, "output_text", None)
    if output_text:
        return str(output_text)
    texts: list[str] = []
    for item in _response_output_items(response):
        if _item_type(item) != "message":
            continue
        for content in _item_get(item, "content", []) or []:
            text = _item_get(content, "text")
            if text:
                texts.append(str(text))
    return "\n\n".join(texts).strip() or "No report text returned."


def _extract_web_queries(response: Any) -> list[str]:
    queries: list[str] = []
    for item in _response_output_items(response):
        if _item_type(item) != "web_search_call":
            continue
        action = _item_get(item, "action", {}) or {}
        for query in _item_get(action, "queries", []) or []:
            text = str(query).strip()
            if text and text not in queries:
                queries.append(text)
    return queries


def _extract_web_sources(response: Any) -> list[dict[str, str]]:
    sources: list[dict[str, str]] = []
    seen = set()
    for item in _response_output_items(response):
        if _item_type(item) != "web_search_call":
            continue
        action = _item_get(item, "action", {}) or {}
        for source in _item_get(action, "sources", []) or []:
            url = str(_item_get(source, "url") or "").strip()
            title = str(_item_get(source, "title") or "").strip()
            key = (url, title)
            if key in seen:
                continue
            seen.add(key)
            sources.append({"title": title, "url": url})
    return sources


def _response_has_web_search(response: Any) -> bool:
    return any(_item_type(item) == "web_search_call" for item in _response_output_items(response))


def _response_output_items(response: Any) -> list[Any]:
    output = getattr(response, "output", None)
    if output is not None:
        return list(output)
    if hasattr(response, "model_dump"):
        return list(response.model_dump().get("output", []))
    if isinstance(response, dict):
        return list(response.get("output", []))
    return []


def _item_type(item: Any) -> str | None:
    return _item_get(item, "type")


def _item_get(item: Any, name: str, default: Any = None) -> Any:
    if isinstance(item, dict):
        return item.get(name, default)
    return getattr(item, name, default)


def _decimal_str(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None


def _create_focused_chart_assets(
    *,
    stock: WatchlistStock,
    snapshots: list[Any],
    reports_dir: Path,
    generated_at: datetime,
) -> list[Path]:
    if not snapshots:
        return []
    chart_dir = reports_dir / "assets" / f"{generated_at:%Y%m%d-%H%M%S}-{stock.symbol.lower()}"
    chart_dir.mkdir(parents=True, exist_ok=True)
    close_path = chart_dir / f"{stock.symbol.lower()}-close-price.png"
    volume_path = chart_dir / f"{stock.symbol.lower()}-volume.png"
    _plot_close_chart(stock=stock, snapshots=snapshots, output_path=close_path)
    _plot_volume_chart(stock=stock, snapshots=snapshots, output_path=volume_path)
    return [close_path, volume_path]


def _plot_close_chart(*, stock: WatchlistStock, snapshots: list[Any], output_path: Path) -> None:
    dates = [snapshot.snapshot_date for snapshot in snapshots if snapshot.close_price is not None]
    closes = [float(snapshot.close_price) for snapshot in snapshots if snapshot.close_price is not None]
    if not dates or not closes:
        return
    fig, ax = plt.subplots(figsize=(10, 4.8), dpi=150)
    ax.plot(dates, closes, color="#0F766E", linewidth=2.4)
    ax.fill_between(dates, closes, min(closes), color="#99F6E4", alpha=0.35)
    ax.set_title(f"{stock.symbol} Close Price Trend", fontsize=14, pad=14)
    ax.set_ylabel("Close")
    ax.grid(alpha=0.18)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(output_path, bbox_inches="tight")
    plt.close(fig)


def _plot_volume_chart(*, stock: WatchlistStock, snapshots: list[Any], output_path: Path) -> None:
    dates = [snapshot.snapshot_date for snapshot in snapshots if snapshot.volume is not None]
    volumes = [snapshot.volume for snapshot in snapshots if snapshot.volume is not None]
    if not dates or not volumes:
        return
    fig, ax = plt.subplots(figsize=(10, 4.8), dpi=150)
    ax.bar(dates, volumes, color="#2563EB", width=0.8)
    ax.set_title(f"{stock.symbol} Volume Trend", fontsize=14, pad=14)
    ax.set_ylabel("Volume")
    ax.grid(axis="y", alpha=0.18)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(output_path, bbox_inches="tight")
    plt.close(fig)


def utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)
