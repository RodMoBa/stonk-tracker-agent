from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from sqlalchemy.orm import Session

from stonk_tracker_agent.analysis import classify_event, detect_outliers, diversification_notes
from stonk_tracker_agent.config import Settings, get_settings
from stonk_tracker_agent.db.models import WatchlistStock
from stonk_tracker_agent.db.repositories import ResearchRepository, WatchlistRepository
from stonk_tracker_agent.llm_research import (
    build_research_llm,
    curate_events_with_llm,
    generate_holding_note_with_llm,
    interpret_outliers_with_llm,
    research_diversification_options_with_llm,
    synthesize_diversification_with_llm,
)
from stonk_tracker_agent.providers.market import MarketDataProvider, YFinanceMarketDataProvider
from stonk_tracker_agent.providers.search import NullSearchProvider, SearchProvider, TavilySearchProvider
from stonk_tracker_agent.reports import render_markdown_report, save_markdown_report


class ReportState(TypedDict, total=False):
    run_started_at: datetime
    run_finished_at: datetime
    stocks: list[Any]
    snapshots: dict[str, list[dict[str, Any]]]
    events: dict[str, list[dict[str, Any]]]
    price_findings: dict[str, list[str]]
    diversification: list[str]
    diversification_ideas: list[dict[str, str]]
    watchlist_ideas: list[dict[str, str]]
    holding_notes: dict[str, dict[str, Any]]
    llm_summary: str | None
    report_title: str
    report_path: str
    messages: list[str]


# Build the end-to-end report workflow and keep each phase isolated so the state
# written by one node can be reused by later nodes and by tests.
def build_report_graph(
    session: Session,
    *,
    settings: Settings | None = None,
    market_provider: MarketDataProvider | None = None,
    search_provider: SearchProvider | None = None,
):
    settings = settings or get_settings()
    market_provider = market_provider or YFinanceMarketDataProvider()
    search_provider = search_provider or (TavilySearchProvider(settings.tavily_api_key) if settings.tavily_api_key else NullSearchProvider())
    research_llm = build_research_llm(settings)
    research_repo = ResearchRepository(session)
    watchlist_repo = WatchlistRepository(session)

    # Normalize ORM objects into JSON-like state so LangGraph can pass them
    # cleanly between nodes without holding live SQLAlchemy objects.
    def stock_to_state(stock: Any) -> dict[str, Any]:
        return {
            "id": stock.id,
            "symbol": stock.symbol,
            "exchange": stock.exchange,
            "country_region": stock.country_region,
            "currency": stock.currency,
            "company_name": stock.company_name,
            "sector": stock.sector,
            "priority": stock.priority,
            "long_term_thesis": stock.long_term_thesis,
            "active": stock.active,
        }

    def stock_from_state(stock: dict[str, Any]) -> WatchlistStock | None:
        return session.get(WatchlistStock, stock["id"])

    # Start from the active control table because the watchlist is the driver
    # for every downstream research step.
    def load_watchlist(state: ReportState) -> ReportState:
        stocks = [stock_to_state(stock) for stock in watchlist_repo.list_active()]
        return {**state, "stocks": stocks, "messages": [*state.get("messages", []), f"Loaded {len(stocks)} active stocks."]}

    # Pull a fresh rolling history for each symbol, then persist it so later
    # analysis reads from the database-backed snapshot history.
    def ingest_price_history(state: ReportState) -> ReportState:
        snapshots: dict[str, list[dict[str, Any]]] = {}
        saved_count = 0
        for stock in state.get("stocks", []):
            history = market_provider.get_history(stock["symbol"], days=90)
            snapshots[stock["symbol"]] = history
            orm_stock = stock_from_state(stock)
            if history and orm_stock:
                saved_count += research_repo.save_price_history(orm_stock, history)
        return {**state, "snapshots": snapshots, "messages": [*state.get("messages", []), f"Stored {saved_count} daily price rows from yfinance."]}

    # Gather recent headlines, let GPT curate them when configured, and then
    # reload the last 30 days from the database so every later node sees the
    # same persisted event set.
    def ingest_events(state: ReportState) -> ReportState:
        events: dict[str, list[dict[str, Any]]] = {}
        since = utc_now().date() - timedelta(days=30)
        saved_count = 0
        curated_count = 0
        for stock in state.get("stocks", []):
            raw_events = search_provider.search_stock_news(symbol=stock["symbol"], company_name=stock.get("company_name"), days=30)
            if research_llm:
                classified = curate_events_with_llm(research_llm, stock=stock, raw_events=raw_events)
            else:
                classified = [classify_event(event) for event in raw_events]
            curated_count += len(classified)
            orm_stock = stock_from_state(stock)
            for event in classified:
                if orm_stock:
                    research_repo.save_event(orm_stock, event)
                    saved_count += 1
            if orm_stock:
                events[stock["symbol"]] = [
                    {
                        "title": item.title,
                        "summary": item.summary,
                        "source_url": item.source_url,
                        "source_name": item.source_name,
                        "event_date": item.event_date,
                        "sentiment": item.sentiment,
                        "impact": item.impact,
                    }
                    for item in research_repo.events_since(orm_stock.id, since)
                ]
            else:
                events[stock["symbol"]] = classified
        llm_note = " with GPT curation" if research_llm else ""
        return {
            **state,
            "events": events,
            "messages": [
                *state.get("messages", []),
                f"Captured {saved_count} event rows{llm_note}; {curated_count} kept after filtering and loaded 30-day event history.",
            ],
        }

    # Combine price history, stored events, and GPT reasoning into the richer
    # per-symbol notes that the report renderer consumes directly.
    def analyze(state: ReportState) -> ReportState:
        price_findings: dict[str, list[str]] = {}
        holding_notes: dict[str, dict[str, Any]] = {}
        for stock in state.get("stocks", []):
            snapshots = research_repo.recent_snapshots(stock["id"], limit=30)
            heuristic_findings = detect_outliers(stock["symbol"], snapshots)
            stock_events = state.get("events", {}).get(stock["symbol"], [])
            interpreted_findings = interpret_outliers_with_llm(
                research_llm,
                stock=stock,
                snapshots=snapshots,
                events=stock_events,
                heuristic_findings=heuristic_findings,
            )
            price_findings[stock["symbol"]] = interpreted_findings
            holding_notes[stock["symbol"]] = generate_holding_note_with_llm(
                research_llm,
                stock=stock,
                snapshots=snapshots,
                events=stock_events,
                outlier_notes=interpreted_findings,
            )
        diversification = (
            synthesize_diversification_with_llm(
                research_llm,
                stocks=state.get("stocks", []),
                events_by_symbol=state.get("events", {}),
            )
            if research_llm
            else diversification_notes(state.get("stocks", []))
        )
        diversification_research = research_diversification_options_with_llm(
            research_llm,
            search_provider=search_provider,
            stocks=state.get("stocks", []),
            diversification_notes_list=diversification,
            events_by_symbol=state.get("events", {}),
        )
        return {
            **state,
            "price_findings": price_findings,
            "diversification": diversification,
            "diversification_ideas": diversification_research.get("ideas", []),
            "watchlist_ideas": diversification_research.get("candidates", []),
            "holding_notes": holding_notes,
            "messages": [
                *state.get("messages", []),
                "Generated GPT research notes, live diversification research ideas, and outlier interpretation."
                if research_llm
                else "Analyzed outliers and diversification.",
            ],
        }

    # The executive summary is a final synthesis pass over everything already
    # computed, not the place where raw research logic happens.
    def summarize(state: ReportState) -> ReportState:
        if not state.get("stocks"):
            return {**state, "llm_summary": None, "messages": [*state.get("messages", []), "Skipped LLM summary; watchlist is empty."]}
        if research_llm is None:
            return {**state, "llm_summary": None, "messages": [*state.get("messages", []), "Skipped LLM summary; OPENAI_API_KEY is not set."]}
        prompt = (
            "You are a portfolio research and diversification assistant. "
            "Analyze the watchlist and write only the Executive Summary section for a larger report. "
            "Do not provide financial advice. Do not tell the user to buy, sell, hold, short, average down, take profit, stop loss, rebalance, or allocate a specific percentage. "
            "Frame outputs as educational research support, hypothesis generation, and due-diligence ideas. "
            "Use language such as research idea, area to investigate, risk to monitor, diversification consideration, possible follow-up question, and not a trade instruction. "
            "Summarize the main watchlist theme, biggest concentration risk, key short-term outliers, long-term research priorities, and diversification areas to investigate. "
            "Keep it concise and specific.\n\n"
            f"Stocks: {[stock['symbol'] for stock in state.get('stocks', [])]}\n"
            f"Outliers: {state.get('price_findings', {})}\n"
            f"Diversification: {state.get('diversification', [])}\n"
            f"Events: {state.get('events', {})}\n"
            f"Holding notes: {state.get('holding_notes', {})}"
        )
        response = research_llm.invoke(prompt)
        return {**state, "llm_summary": response.content, "messages": [*state.get("messages", []), "Generated LLM summary."]}

    # Render the final markdown artifact and store report metadata so the UI
    # can list prior runs without re-executing the graph.
    def persist_report(state: ReportState) -> ReportState:
        finished_at = utc_now()
        title, content = render_markdown_report(
            stocks=state.get("stocks", []),
            price_findings=state.get("price_findings", {}),
            events=state.get("events", {}),
            diversification=state.get("diversification", []),
            diversification_ideas=state.get("diversification_ideas", []),
            watchlist_ideas=state.get("watchlist_ideas", []),
            holding_notes=state.get("holding_notes", {}),
            llm_summary=state.get("llm_summary"),
            generated_at=finished_at,
        )
        path = save_markdown_report(settings.reports_dir, title, content, finished_at)
        research_repo.save_report(
            title=title,
            markdown_path=path,
            symbols_covered=[stock["symbol"] for stock in state.get("stocks", [])],
            run_started_at=state["run_started_at"],
            run_finished_at=finished_at,
            summary=state.get("llm_summary"),
        )
        return {
            **state,
            "run_finished_at": finished_at,
            "report_title": title,
            "report_path": str(path),
            "messages": [*state.get("messages", []), f"Saved report to {path}."],
        }

    # The node order mirrors the intended research pipeline from ingestion to
    # interpretation to final report persistence.
    graph = StateGraph(ReportState)
    graph.add_node("load_watchlist", load_watchlist)
    graph.add_node("ingest_price_history", ingest_price_history)
    graph.add_node("ingest_events", ingest_events)
    graph.add_node("analyze", analyze)
    graph.add_node("summarize", summarize)
    graph.add_node("persist_report", persist_report)
    graph.add_edge(START, "load_watchlist")
    graph.add_edge("load_watchlist", "ingest_price_history")
    graph.add_edge("ingest_price_history", "ingest_events")
    graph.add_edge("ingest_events", "analyze")
    graph.add_edge("analyze", "summarize")
    graph.add_edge("summarize", "persist_report")
    graph.add_edge("persist_report", END)
    return graph.compile(checkpointer=MemorySaver())


# Keep the public entrypoint thin so callers can swap settings or thread ids
# without needing to know how the graph itself is assembled.
def run_report(session: Session, thread_id: str = "daily-report", settings: Settings | None = None) -> ReportState:
    graph = build_report_graph(session, settings=settings)
    return graph.invoke(
        {"run_started_at": utc_now(), "messages": []},
        config={"configurable": {"thread_id": thread_id}},
    )


def utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)
