from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from stonk_tracker_agent.chat import answer_research_question
from stonk_tracker_agent.config import OPENAI_REPORT_MODEL_OPTIONS, get_settings
from stonk_tracker_agent.db.base import Base
from stonk_tracker_agent.db.repositories import ResearchRepository, WatchlistRepository
from stonk_tracker_agent.db.session import SessionLocal, engine
from stonk_tracker_agent.focused_research import generate_focused_stock_report
from stonk_tracker_agent.graph import run_report
from stonk_tracker_agent.reports import render_pdf_report
from stonk_tracker_agent.watchlist_enrichment import enrich_and_save_stock


st.set_page_config(page_title="Stonk Tracker Agent", layout="wide")


@st.cache_resource
def ensure_schema() -> None:
    Base.metadata.create_all(bind=engine)


ensure_schema()

st.title("Stonk Tracker Agent")

tab_watchlist, tab_run, tab_focused, tab_reports, tab_chat = st.tabs(
    ["Watchlist", "Run Report", "Focused Research", "Reports", "Agent Chat"]
)

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
            company_name = cols[1].text_input("Company name override", placeholder="Optional")
            currency = cols[2].selectbox("Currency", ["USD", "EUR"])
            priority = st.number_input("Priority", min_value=1, max_value=5, value=3)
            manual_notes = st.text_area("Manual thesis notes", placeholder="Optional; the app will generate the long-term thesis from profile and recent news.")
            active = st.checkbox("Active", value=True)
            submitted = st.form_submit_button("Research and save stock")
        if submitted and symbol:
            with st.status("Researching stock before saving", expanded=True) as status:
                result = enrich_and_save_stock(
                    session,
                    symbol=symbol,
                    preferred_currency=currency,
                    company_name=company_name or None,
                    priority=int(priority),
                    manual_notes=manual_notes or None,
                    active=active,
                )
                st.write(f"Generated profile: exchange={result.stock.exchange or 'unknown'}, country={result.stock.country_region or 'unknown'}, sector={result.stock.sector or 'unknown'}")
                st.write(f"Saved {result.events_saved} recent news events.")
                st.write(f"Saved {result.prices_saved} daily price rows.")
                status.update(label="Stock saved", state="complete")
            st.success(f"Saved {result.stock.symbol}. Refreshing...")
            st.rerun()

with tab_run:
    st.subheader("Generate Research Report")
    st.write("Runs the LangGraph workflow for the active watchlist and saves a local markdown report.")
    settings = get_settings()
    default_model_index = next(
        (index for index, item in enumerate(OPENAI_REPORT_MODEL_OPTIONS) if item["id"] == settings.openai_model),
        0,
    )
    selected_model = st.selectbox(
        "OpenAI model",
        OPENAI_REPORT_MODEL_OPTIONS,
        index=default_model_index,
        format_func=lambda item: item["label"],
        help="Cost tags are standard API prices per 1M tokens. Pro models are intentionally excluded.",
    )
    if st.button("Run report", type="primary"):
        with st.status("Running research workflow", expanded=True) as status:
            with SessionLocal() as session:
                run_settings = settings.model_copy(update={"openai_model": selected_model["id"]})
                result = run_report(session, settings=run_settings)
            for message in result.get("messages", []):
                st.write(message)
            status.update(label="Report completed", state="complete")
        report_path = result.get("report_path")
        if report_path:
            st.success(f"Saved report: {report_path}")

with tab_focused:
    st.subheader("Focused Research")
    st.write("Generate a single-stock deep-dive using stored database context plus explicit OpenAI web search.")
    settings = get_settings()
    with SessionLocal() as session:
        focused_stocks = WatchlistRepository(session).list_active()
        focused_reports_repo = ResearchRepository(session)
        if not focused_stocks:
            st.info("Add active watchlist stocks before running focused research.")
        else:
            selected_stock = st.selectbox(
                "Stock",
                focused_stocks,
                format_func=lambda item: f"{item.symbol} - {item.company_name or item.symbol}",
                key="focused_stock_select",
            )
            default_focused_model_index = next(
                (index for index, item in enumerate(OPENAI_REPORT_MODEL_OPTIONS) if item["id"] == settings.openai_model),
                0,
            )
            selected_focused_model = st.selectbox(
                "OpenAI model",
                OPENAI_REPORT_MODEL_OPTIONS,
                index=default_focused_model_index,
                format_func=lambda item: item["label"],
                key="focused_model_select",
                help="This screen uses OpenAI web search explicitly and shows the search trace below the report.",
            )

            snapshot_rows = list(reversed(focused_reports_repo.recent_snapshots(selected_stock.id, limit=60)))
            if snapshot_rows:
                chart_data = pd.DataFrame(
                    [
                        {
                            "date": snapshot.snapshot_date,
                            "close": float(snapshot.close_price) if snapshot.close_price is not None else None,
                            "volume": snapshot.volume,
                        }
                        for snapshot in snapshot_rows
                    ]
                ).set_index("date")
                metrics = st.columns(3)
                latest_close = chart_data["close"].dropna().iloc[-1] if not chart_data["close"].dropna().empty else None
                prev_close = chart_data["close"].dropna().iloc[-2] if len(chart_data["close"].dropna()) >= 2 else None
                five_day_base = chart_data["close"].dropna().iloc[-5] if len(chart_data["close"].dropna()) >= 5 else None
                one_day_change = ((latest_close - prev_close) / prev_close * 100) if latest_close and prev_close else None
                five_day_change = ((latest_close - five_day_base) / five_day_base * 100) if latest_close and five_day_base else None
                metrics[0].metric("Latest close", f"{latest_close:.2f}" if latest_close is not None else "N/A")
                metrics[1].metric("1D change", f"{one_day_change:.2f}%" if one_day_change is not None else "N/A")
                metrics[2].metric("5D change", f"{five_day_change:.2f}%" if five_day_change is not None else "N/A")
                chart_cols = st.columns(2)
                chart_cols[0].line_chart(chart_data[["close"]], height=280, use_container_width=True)
                chart_cols[1].bar_chart(chart_data[["volume"]], height=280, use_container_width=True)

            if st.button("Run focused research", type="primary", key="run_focused_research"):
                with st.status("Running focused OpenAI web research", expanded=True) as status:
                    focused_settings = settings.model_copy(update={"openai_model": selected_focused_model["id"]})
                    result = generate_focused_stock_report(
                        session,
                        stock_id=selected_stock.id,
                        model=selected_focused_model["id"],
                        settings=focused_settings,
                    )
                    st.session_state.focused_research_result = result
                    status.update(label="Focused research completed", state="complete")

            focused_result = st.session_state.get("focused_research_result")
            if focused_result and focused_result.stock_symbol == selected_stock.symbol:
                st.success(f"Saved focused report: {focused_result.markdown_path}")
                trace_cols = st.columns(2)
                trace_cols[0].metric("OpenAI web search used", "Yes" if focused_result.web_search_used else "No trace found")
                trace_cols[1].metric("Web sources captured", str(len(focused_result.web_sources)))
                if focused_result.chart_paths:
                    st.subheader("Report Visuals")
                    visual_cols = st.columns(len(focused_result.chart_paths))
                    for index, chart_path in enumerate(focused_result.chart_paths):
                        if chart_path.exists():
                            visual_cols[index].image(str(chart_path), use_container_width=True)
                st.download_button(
                    "Export focused report as PDF",
                    data=focused_result.pdf_bytes,
                    file_name=f"{Path(focused_result.markdown_path).stem}.pdf",
                    mime="application/pdf",
                    key="focused_pdf_download",
                )
                if focused_result.web_queries:
                    with st.expander("Web search queries used", expanded=False):
                        for query in focused_result.web_queries:
                            st.write(f"- {query}")
                if focused_result.web_sources:
                    with st.expander("Web sources consulted", expanded=False):
                        for source in focused_result.web_sources:
                            url = source.get("url")
                            title = source.get("title") or url or "source"
                            st.markdown(f"- [{title}]({url})" if url else f"- {title}")
                st.markdown(focused_result.markdown)

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
            markdown_content = path.read_text(encoding="utf-8")
            pdf_bytes = render_pdf_report(markdown_content, title=selected.title)
            st.download_button(
                "Export report as PDF",
                data=pdf_bytes,
                file_name=f"{path.stem}.pdf",
                mime="application/pdf",
            )
            st.markdown(markdown_content)
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
