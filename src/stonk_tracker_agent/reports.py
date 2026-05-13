from __future__ import annotations

from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, Preformatted, SimpleDocTemplate, Spacer, Table, TableStyle

from stonk_tracker_agent.analysis import candidate_watchlist_research_ideas, diversification_research_ideas


DISCLAIMER = (
    "This report is for research and educational support only. It is not financial advice, investment advice, "
    "a recommendation, or an instruction to buy, sell, hold, or trade any security. Any action ideas are research tasks only."
)

FINAL_NOTE = (
    "None of the above is financial advice. The purpose of this report is to organize research, identify risks, "
    "and generate due-diligence questions before any independent decision-making or professional consultation."
)


def render_markdown_report(
    *,
    stocks: list[Any],
    price_findings: dict[str, list[str]],
    events: dict[str, list[dict[str, Any]]],
    diversification: list[str],
    holding_notes: dict[str, dict[str, Any]] | None = None,
    llm_summary: str | None,
    generated_at: datetime,
) -> tuple[str, str]:
    title = f"Stonk Portfolio Research Report - {generated_at:%Y-%m-%d %H:%M}"
    lines = [
        f"# {title}",
        "",
        "## Disclaimer",
        "",
        DISCLAIMER,
        "",
        "## Executive Summary",
        "",
        _clean_llm_summary(llm_summary) or _fallback_executive_summary(stocks=stocks, price_findings=price_findings),
        "",
        "## Portfolio Diversification Review",
        "",
    ]
    lines.extend(f"- {note}" for note in diversification)
    lines.extend(
        [
            "- Theme exposure: review whether holdings share the same AI, software, growth, commodity, rates, or macro-cycle narrative.",
            "- Geographic and currency exposure: compare tagged countries and currencies against desired research coverage.",
            "- Volatility/liquidity risk: compare daily volume, gap risk, and price ranges before interpreting short-term moves.",
            "- Correlation risk: research whether holdings respond to the same catalysts, customer budgets, funding cycles, or valuation multiples.",
            "- Event/catalyst dependency: separate durable thesis evidence from one-off headlines, earnings surprises, and news-driven moves.",
            "",
            "Potential diversification research areas include the categories below. These are comparison areas, not trade instructions.",
            "",
            "| Area to research | Examples | Why it may matter |",
            "| --- | --- | --- |",
        ]
    )
    for idea in diversification_research_ideas(stocks):
        lines.append(f"| {idea['area']} | {idea['examples']} | {idea['why']} |")

    lines.extend(["", "## Holding-by-Holding Research Notes", ""])
    if not stocks:
        lines.append("No active watchlist stocks found.")
    for stock in stocks:
        symbol = _field(stock, "symbol")
        name = _field(stock, "company_name") or symbol
        exchange = _field(stock, "exchange") or "N/A"
        sector = _field(stock, "sector") or "Unknown"
        region = _field(stock, "country_region") or "Unknown"
        currency = _field(stock, "currency") or "Unknown"
        priority = _field(stock, "priority")
        thesis = _field(stock, "long_term_thesis") or "No thesis stored yet; research business model, fundamentals, catalysts, and risks."
        stock_events = events.get(symbol, [])
        note = (holding_notes or {}).get(symbol, {})
        lines.extend(
            [
                f"### {symbol} - {name}",
                "",
                f"- Facts: exchange `{exchange}`, sector `{sector}`, region `{region}`, currency `{currency}`, priority `{priority}`.",
                f"- Current thesis summary: {note.get('thesis_summary') or thesis}",
                f"- Main positive drivers to research: {_join_items(note.get('positive_drivers')) or 'Revenue durability, margin trend, balance sheet quality, product/customer momentum, and whether recent news supports the thesis.'}",
                f"- Main risks to monitor: {_join_items(note.get('risks')) or 'Valuation sensitivity, liquidity, customer concentration, funding conditions, competition, execution risk, and repeated negative catalysts.'}",
                f"- Recent event interpretation: {note.get('recent_event_interpretation') or _event_interpretation(stock_events)}",
                f"- Key metrics to monitor: {_join_items(note.get('metrics_to_monitor')) or 'Revenue growth, free cash flow, gross/operating margins, debt maturity profile, volume/liquidity, valuation multiples, and catalyst calendar.'}",
                f"- Research questions for the next 1-4 quarters: {_join_items(note.get('research_questions')) or 'What evidence would strengthen or weaken the thesis? Are news-driven moves confirmed by fundamentals? Is risk concentrated in the same macro or sector narrative as other holdings?'}",
                f"- Research-only action ideas: {_join_items(note.get('research_actions')) or 'Compare this company with sector peers, review the next earnings transcript, track segment growth, and build a catalyst calendar.'} This is not a trade instruction.",
                "",
            ]
        )

    lines.extend(["", "## Short-Term Signals", ""])
    for symbol, findings in price_findings.items():
        lines.append(f"### {symbol}")
        for finding in findings:
            lines.append(f"- {finding} This is a research flag, not a trade signal; review the related catalyst, liquidity, and whether fundamentals confirm the move.")

    lines.extend(["", "## Recent Events", ""])
    for symbol, stock_events in events.items():
        lines.append(f"### {symbol}")
        if not stock_events:
            lines.append("- No recent web events captured.")
        for event in stock_events:
            source = f" [{event.get('source_name') or 'source'}]({event.get('source_url')})" if event.get("source_url") else ""
            lines.append(f"- **{event.get('impact', 'low')} / {event.get('sentiment', 'neutral')}**: {event.get('title')}{source}")
            if _should_render_event_summary(event):
                lines.append(f"  {str(event['summary'])[:1200]}")

    lines.extend(["", "## Cross-Holding Risk Notes", ""])
    lines.extend(_cross_holding_risk_notes(stocks))

    lines.extend(["", "## Diversification Research Ideas", ""])
    lines.append("Diversification comments identify areas to investigate, not assets to buy or allocations to implement.")
    for idea in candidate_watchlist_research_ideas(stocks):
        lines.extend(["", f"### {idea['ticker']} - {idea['name']}", "", idea["angle"]])

    lines.extend(
        [
            "",
            "## Research Action Ideas",
            "",
            "| Action idea | Why it matters | Data needed | Priority | Time horizon | Not financial advice note |",
            "| --- | --- | --- | --- | --- | --- |",
            "| Compare sector exposure against a broad benchmark | Identifies concentration and narrative risk | Current holdings by sector; benchmark sector weights | High | This week | Research task only, not a trade instruction |",
            "| Build a catalyst calendar | Separates scheduled events from surprise headlines | Earnings dates, product events, regulatory dates, debt maturities | High | 1-4 quarters | Research task only, not a trade instruction |",
            "| Track revenue growth by segment | Tests whether the long-term thesis is supported by fundamentals | Quarterly revenue by segment and guidance | High | 2-4 quarters | Research task only, not a trade instruction |",
            "| Review whether valuation is supported by cash-flow growth | Helps stress-test growth assumptions | Free cash flow, margins, valuation multiples, peer comps | Medium | 1-2 quarters | Research task only, not a trade instruction |",
            "| Collect more price and volume snapshots before interpreting short-term outliers | Reduces overreaction to one-day moves | Daily close, volume, volatility history | Medium | 30-90 days | Research task only, not a trade instruction |",
            "| Compare company risk with adjacent sectors | Surfaces possible diversification research areas | Sector peers, ETFs, industry revenue drivers | Medium | This month | Research task only, not a trade instruction |",
            "| Monitor whether news-driven moves are confirmed by fundamentals | Avoids confusing headlines with thesis evidence | News history, earnings data, segment metrics | High | Ongoing | Research task only, not a trade instruction |",
            "",
            "## Final Note",
            "",
            FINAL_NOTE,
        ]
    )
    summary = llm_summary or "Long-term-first research report generated."
    return title, "\n".join(lines) + "\n"


def save_markdown_report(reports_dir: Path, title: str, content: str, generated_at: datetime) -> Path:
    reports_dir.mkdir(parents=True, exist_ok=True)
    safe_title = "".join(char if char.isalnum() else "-" for char in title.lower()).strip("-")
    path = reports_dir / f"{generated_at:%Y%m%d-%H%M%S}-{safe_title[:80]}.md"
    path.write_text(content, encoding="utf-8")
    return path


def render_pdf_report(markdown_content: str, *, title: str = "Stonk Portfolio Research Report") -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=0.55 * inch,
        leftMargin=0.55 * inch,
        topMargin=0.55 * inch,
        bottomMargin=0.55 * inch,
        title=title,
    )
    styles = getSampleStyleSheet()
    body = ParagraphStyle("StonkBody", parent=styles["BodyText"], fontSize=9, leading=12, spaceAfter=6, alignment=TA_LEFT)
    h1 = ParagraphStyle("StonkH1", parent=styles["Heading1"], fontSize=18, leading=22, spaceAfter=12)
    h2 = ParagraphStyle("StonkH2", parent=styles["Heading2"], fontSize=14, leading=17, spaceBefore=10, spaceAfter=8)
    h3 = ParagraphStyle("StonkH3", parent=styles["Heading3"], fontSize=11, leading=14, spaceBefore=8, spaceAfter=6)
    bullet = ParagraphStyle("StonkBullet", parent=body, leftIndent=14, firstLineIndent=-8)
    code = ParagraphStyle("StonkCode", parent=styles["Code"], fontSize=7, leading=9)
    table_cell = ParagraphStyle("StonkTableCell", parent=body, fontSize=7, leading=9)

    story: list[Any] = []
    lines = markdown_content.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index].rstrip()
        if not line:
            story.append(Spacer(1, 5))
            index += 1
            continue
        if line.startswith("|") and index + 1 < len(lines) and _is_markdown_table_separator(lines[index + 1]):
            table_lines = [line]
            index += 2
            while index < len(lines) and lines[index].startswith("|"):
                table_lines.append(lines[index].rstrip())
                index += 1
            story.append(_markdown_table_to_pdf(table_lines, table_cell))
            story.append(Spacer(1, 8))
            continue
        if line.startswith("# "):
            story.append(Paragraph(_inline_markdown_to_pdf(line[2:]), h1))
        elif line.startswith("## "):
            story.append(Paragraph(_inline_markdown_to_pdf(line[3:]), h2))
        elif line.startswith("### "):
            story.append(Paragraph(_inline_markdown_to_pdf(line[4:]), h3))
        elif line.startswith("- "):
            story.append(Paragraph(f"- {_inline_markdown_to_pdf(line[2:])}", bullet))
        elif line.startswith("  "):
            story.append(Preformatted(line.strip(), code))
        else:
            story.append(Paragraph(_inline_markdown_to_pdf(line), body))
        index += 1

    doc.build(story)
    return buffer.getvalue()


def _field(item: Any, name: str) -> Any:
    if isinstance(item, dict):
        return item.get(name)
    return getattr(item, name)


def _clean_llm_summary(summary: str | None) -> str | None:
    if not summary:
        return None
    lines = str(summary).strip().splitlines()
    while lines and lines[0].strip().lower().lstrip("# ").startswith("executive summary"):
        lines.pop(0)
    return "\n".join(lines).strip() or None


def _is_markdown_table_separator(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith("|") and set(stripped.replace("|", "").replace(" ", "")) <= {"-", ":"}


def _markdown_table_to_pdf(table_lines: list[str], style: ParagraphStyle) -> Table:
    rows = []
    for line in table_lines:
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        rows.append([Paragraph(_inline_markdown_to_pdf(cell), style) for cell in cells])
    table = Table(rows, repeatRows=1, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E8EEF7")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#172033")),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#B8C2D2")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return table


def _inline_markdown_to_pdf(text: str) -> str:
    cleaned = escape(text).replace("`", "")
    parts = cleaned.split("**")
    if len(parts) == 1:
        return cleaned
    rendered = parts[0]
    for index, part in enumerate(parts[1:], start=1):
        rendered += f"<b>{part}</b>" if index % 2 == 1 else part
    return rendered


def _fallback_executive_summary(*, stocks: list[Any], price_findings: dict[str, list[str]]) -> str:
    if not stocks:
        return "No active watchlist stocks were found. Add holdings before concentration, thesis, and diversification research can be meaningfully analyzed."
    sectors = sorted({(_field(stock, "sector") or "Unknown") for stock in stocks})
    outlier_count = sum(1 for findings in price_findings.values() for finding in findings if "No major" not in finding)
    return (
        f"The current watchlist has {len(stocks)} active holdings across these tagged sectors: {', '.join(sectors)}. "
        "The main concentration research priority is to review whether holdings share the same sector, AI/software/growth, liquidity, or catalyst narrative. "
        f"Short-term signal count requiring research review: {outlier_count}. "
        "Diversification areas to investigate include defensive sectors, healthcare, industrials, international exposure, fixed income, broad ETFs, and cash-flow focused businesses."
    )


def _event_interpretation(stock_events: list[dict[str, Any]]) -> str:
    if not stock_events:
        return "No recent stored events were found; collect more news history before drawing conclusions."
    titles = [event.get("title") for event in stock_events[:3] if event.get("title")]
    return "Recent stored events to review include: " + "; ".join(titles) + ". Treat these as due-diligence prompts, not trade signals."


def _should_render_event_summary(event: dict[str, Any]) -> bool:
    source_name = str(event.get("source_name") or "").lower()
    summary = str(event.get("summary") or "").strip()
    if not summary:
        return False
    return source_name == "yahoo finance"


def _join_items(value: Any) -> str | None:
    if not isinstance(value, list):
        return None
    items = [" ".join(str(item).split()).strip() for item in value if str(item).strip()]
    return "; ".join(items) if items else None


def _cross_holding_risk_notes(stocks: list[Any]) -> list[str]:
    if not stocks:
        return ["- No cross-holding risks can be assessed until active holdings exist."]
    sectors = sorted({(_field(stock, "sector") or "Unknown") for stock in stocks})
    regions = sorted({(_field(stock, "country_region") or "Unknown") for stock in stocks})
    currencies = sorted({(_field(stock, "currency") or "Unknown") for stock in stocks})
    return [
        f"- Same-sector exposure to research: {', '.join(sectors)}.",
        "- Shared narrative risk: review whether holdings depend on the same AI, software, growth, commodity, rates, or macro-cycle assumptions.",
        "- Customer and funding sensitivity: compare end customers, capital needs, refinancing risk, and dependency on external financing.",
        f"- Geographic exposure to research: {', '.join(regions)}.",
        f"- Currency exposure to research: {', '.join(currencies)}.",
        "- Valuation risk: compare whether multiple expansion, revenue growth, or cash-flow growth is doing most of the thesis work.",
    ]
