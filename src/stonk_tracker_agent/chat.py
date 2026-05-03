from __future__ import annotations

from langchain_openai import ChatOpenAI
from sqlalchemy.orm import Session

from stonk_tracker_agent.config import get_settings
from stonk_tracker_agent.db.repositories import AgentThreadRepository, ResearchRepository, WatchlistRepository


def answer_research_question(session: Session, question: str, thread_id: str = "streamlit-chat") -> str:
    settings = get_settings()
    AgentThreadRepository(session).ensure(thread_id=thread_id, purpose="chat", title="Streamlit research chat")
    stocks = WatchlistRepository(session).list_active()
    research_repo = ResearchRepository(session)
    context = []
    for stock in stocks:
        snapshots = research_repo.recent_snapshots(stock.id, limit=3)
        events = research_repo.recent_events(stock.id, limit=5)
        context.append(
            {
                "symbol": stock.symbol,
                "company": stock.company_name,
                "sector": stock.sector,
                "thesis": stock.long_term_thesis,
                "snapshots": [
                    {"date": snap.snapshot_date.isoformat(), "close": str(snap.close_price), "volume": snap.volume}
                    for snap in snapshots
                ],
                "events": [
                    {"title": event.title, "sentiment": event.sentiment, "impact": event.impact, "url": event.source_url}
                    for event in events
                ],
            }
        )
    if not settings.openai_api_key:
        return "OPENAI_API_KEY is not configured, so chat synthesis is disabled. Set the environment variable and restart Streamlit."
    llm = ChatOpenAI(model=settings.openai_model, api_key=settings.openai_api_key, temperature=0.2)
    response = llm.invoke(
        "You are a long-term-first portfolio research assistant. "
        "Answer with evidence from the provided watchlist context. "
        "Do not claim to execute trades and do not give autonomous trading instructions.\n\n"
        f"Context: {context}\n\nQuestion: {question}"
    )
    return str(response.content)
