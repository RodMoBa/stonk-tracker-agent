from __future__ import annotations

from pathlib import Path

import streamlit as st

from stonk_tracker_agent.chat import answer_research_question
from stonk_tracker_agent.db.base import Base
from stonk_tracker_agent.db.repositories import ResearchRepository, WatchlistRepository
from stonk_tracker_agent.db.session import SessionLocal, engine
from stonk_tracker_agent.graph import run_report


st.set_page_config(page_title="Stonk Tracker Agent", layout="wide")


@st.cache_resource
def ensure_schema() -> None:
    Base.metadata.create_all(bind=engine)


ensure_schema()

st.title("Stonk Tracker Agent")

tab_watchlist, tab_run, tab_reports, tab_chat = st.tabs(["Watchlist", "Run Report", "Reports", "Agent Chat"])

with tab_watchlist:
    with SessionLocal() as session:
        repo = WatchlistRepository(session)
        stocks = repo.list_all()
        st.subheader("Watchlist")
        if stocks:
            st.dataframe(
                [
                    {
                        "id": stock.id,
                        "symbol": stock.symbol,
                        "exchange": stock.exchange,
                        "company": stock.company_name,
                        "sector": stock.sector,
                        "region": stock.country_region,
                        "currency": stock.currency,
                        "priority": stock.priority,
                        "active": stock.active,
                    }
                    for stock in stocks
                ],
                use_container_width=True,
            )
        else:
            st.info("No stocks yet. Add one below.")

        with st.form("stock_form", clear_on_submit=False):
            cols = st.columns(3)
            symbol = cols[0].text_input("Symbol", placeholder="MSFT")
            exchange = cols[1].text_input("Exchange", placeholder="NASDAQ")
            company_name = cols[2].text_input("Company name", placeholder="Microsoft")
            cols = st.columns(4)
            sector = cols[0].text_input("Sector", placeholder="Technology")
            country_region = cols[1].text_input("Country/region", placeholder="US")
            currency = cols[2].text_input("Currency", placeholder="USD")
            priority = cols[3].number_input("Priority", min_value=1, max_value=5, value=3)
            long_term_thesis = st.text_area("Long-term thesis")
            active = st.checkbox("Active", value=True)
            submitted = st.form_submit_button("Save stock")
            if submitted and symbol:
                repo.upsert(
                    symbol=symbol,
                    exchange=exchange or None,
                    country_region=country_region or None,
                    currency=currency or None,
                    company_name=company_name or None,
                    sector=sector or None,
                    priority=int(priority),
                    long_term_thesis=long_term_thesis or None,
                    active=active,
                )
                st.success(f"Saved {symbol.upper()}. Refreshing...")
                st.rerun()

with tab_run:
    st.subheader("Generate Research Report")
    st.write("Runs the LangGraph workflow for the active watchlist and saves a local markdown report.")
    if st.button("Run report", type="primary"):
        with st.status("Running research workflow", expanded=True) as status:
            with SessionLocal() as session:
                result = run_report(session)
            for message in result.get("messages", []):
                st.write(message)
            status.update(label="Report completed", state="complete")
        report_path = result.get("report_path")
        if report_path:
            st.success(f"Saved report: {report_path}")

with tab_reports:
    st.subheader("Saved Reports")
    with SessionLocal() as session:
        reports = ResearchRepository(session).list_reports()
    if not reports:
        st.info("No reports saved yet.")
    else:
        selected = st.selectbox("Report", reports, format_func=lambda item: f"{item.run_finished_at:%Y-%m-%d %H:%M} - {item.title}")
        path = Path(selected.markdown_path)
        if path.exists():
            st.markdown(path.read_text(encoding="utf-8"))
        else:
            st.warning(f"Report file not found at {path}.")

with tab_chat:
    st.subheader("Research Chat")
    if "messages" not in st.session_state:
        st.session_state.messages = []
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
    prompt = st.chat_input("Ask about your watchlist, reports, catalysts, or diversification")
    if prompt:
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        with st.chat_message("assistant"):
            with st.spinner("Researching..."):
                with SessionLocal() as session:
                    answer = answer_research_question(session, prompt)
                st.markdown(answer)
        st.session_state.messages.append({"role": "assistant", "content": answer})

