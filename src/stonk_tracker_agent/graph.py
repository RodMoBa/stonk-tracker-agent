from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, TypedDict

from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from sqlalchemy.orm import Session

from stonk_tracker_agent.analysis import classify_event, detect_outliers, diversification_notes
from stonk_tracker_agent.config import Settings, get_settings
from stonk_tracker_agent.db.models import WatchlistStock
from stonk_tracker_agent.db.repositories import ResearchRepository, WatchlistRepository
from stonk_tracker_agent.providers.market import AlphaVantageMarketDataProvider, MarketDataProvider, NullMarketDataProvider
from stonk_tracker_agent.providers.search import NullSearchProvider, SearchProvider, TavilySearchProvider
from stonk_tracker_agent.reports import render_markdown_report, save_markdown_report


class ReportState(TypedDict, total=False):
    run_started_at: datetime
    run_finished_at: datetime
    stocks: list[Any]
    snapshots: dict[str, dict[str, Any] | None]
    events: dict[str, list[dict[str, Any]]]
    price_findings: dict[str, list[str]]
    diversification: list[str]
    llm_summary: str | None
    report_title: str
    report_path: str
    messages: list[str]


def build_report_graph(
    session: Session,
    *,
    settings: Settings | None = None,
    market_provider: MarketDataProvider | None = None,
    search_provider: SearchProvider | None = None,
):
    settings = settings or get_settings()
    market_provider = market_provider or (
        AlphaVantageMarketDataProvider(settings.alpha_vantage_api_key)
        if settings.alpha_vantage_api_key
        else NullMarketDataProvider()
    )
    search_provider = search_provider or (TavilySearchProvider(settings.tavily_api_key) if settings.tavily_api_key else NullSearchProvider())
    research_repo = ResearchRepository(session)
    watchlist_repo = WatchlistRepository(session)

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

    def load_watchlist(state: ReportState) -> ReportState:
        stocks = [stock_to_state(stock) for stock in watchlist_repo.list_active()]
        return {**state, "stocks": stocks, "messages": [*state.get("messages", []), f"Loaded {len(stocks)} active stocks."]}

    def fetch_prices(state: ReportState) -> ReportState:
        snapshots: dict[str, dict[str, Any] | None] = {}
        for stock in state.get("stocks", []):
            snapshot = market_provider.get_snapshot(stock["symbol"])
            snapshots[stock["symbol"]] = snapshot
            orm_stock = stock_from_state(stock)
            if snapshot and orm_stock:
                research_repo.save_price_snapshot(orm_stock, snapshot)
        return {**state, "snapshots": snapshots, "messages": [*state.get("messages", []), "Fetched market snapshots."]}

    def search_events(state: ReportState) -> ReportState:
        events: dict[str, list[dict[str, Any]]] = {}
        for stock in state.get("stocks", []):
            raw_events = search_provider.search_stock_news(symbol=stock["symbol"], company_name=stock.get("company_name"))
            classified = [classify_event(event) for event in raw_events]
            events[stock["symbol"]] = classified
            orm_stock = stock_from_state(stock)
            for event in classified:
                if orm_stock:
                    research_repo.save_event(orm_stock, event)
        return {**state, "events": events, "messages": [*state.get("messages", []), "Captured recent web events."]}

    def analyze(state: ReportState) -> ReportState:
        price_findings = {}
        for stock in state.get("stocks", []):
            price_findings[stock["symbol"]] = detect_outliers(stock["symbol"], research_repo.recent_snapshots(stock["id"]))
        diversification = diversification_notes(state.get("stocks", []))
        return {
            **state,
            "price_findings": price_findings,
            "diversification": diversification,
            "messages": [*state.get("messages", []), "Analyzed outliers and diversification."],
        }

    def summarize(state: ReportState) -> ReportState:
        if not state.get("stocks"):
            return {**state, "llm_summary": None, "messages": [*state.get("messages", []), "Skipped LLM summary; watchlist is empty."]}
        if not settings.openai_api_key:
            return {**state, "llm_summary": None, "messages": [*state.get("messages", []), "Skipped LLM summary; OPENAI_API_KEY is not set."]}
        llm = ChatOpenAI(model=settings.openai_model, api_key=settings.openai_api_key, temperature=0.2)
        prompt = (
            "Write a concise long-term-first portfolio research summary. "
            "Do not give autonomous trading instructions. Mention action ideas only as research support.\n\n"
            f"Stocks: {[stock['symbol'] for stock in state.get('stocks', [])]}\n"
            f"Outliers: {state.get('price_findings', {})}\n"
            f"Diversification: {state.get('diversification', [])}\n"
            f"Events: {state.get('events', {})}"
        )
        response = llm.invoke(prompt)
        return {**state, "llm_summary": response.content, "messages": [*state.get("messages", []), "Generated LLM summary."]}

    def persist_report(state: ReportState) -> ReportState:
        finished_at = utc_now()
        title, content = render_markdown_report(
            stocks=state.get("stocks", []),
            price_findings=state.get("price_findings", {}),
            events=state.get("events", {}),
            diversification=state.get("diversification", []),
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

    graph = StateGraph(ReportState)
    graph.add_node("load_watchlist", load_watchlist)
    graph.add_node("fetch_prices", fetch_prices)
    graph.add_node("search_events", search_events)
    graph.add_node("analyze", analyze)
    graph.add_node("summarize", summarize)
    graph.add_node("persist_report", persist_report)
    graph.add_edge(START, "load_watchlist")
    graph.add_edge("load_watchlist", "fetch_prices")
    graph.add_edge("fetch_prices", "search_events")
    graph.add_edge("search_events", "analyze")
    graph.add_edge("analyze", "summarize")
    graph.add_edge("summarize", "persist_report")
    graph.add_edge("persist_report", END)
    return graph.compile(checkpointer=MemorySaver())


def run_report(session: Session, thread_id: str = "daily-report") -> ReportState:
    graph = build_report_graph(session)
    return graph.invoke(
        {"run_started_at": utc_now(), "messages": []},
        config={"configurable": {"thread_id": thread_id}},
    )


def utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)
