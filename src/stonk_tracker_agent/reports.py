from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any


def render_markdown_report(
    *,
    stocks: list[Any],
    price_findings: dict[str, list[str]],
    events: dict[str, list[dict[str, Any]]],
    diversification: list[str],
    llm_summary: str | None,
    generated_at: datetime,
) -> tuple[str, str]:
    title = f"Stonk Portfolio Research Report - {generated_at:%Y-%m-%d %H:%M}"
    lines = [
        f"# {title}",
        "",
        "> Research support only. This report does not place trades or provide autonomous trading instructions.",
        "",
        "## Executive Summary",
        "",
        llm_summary or "Automated research run completed. Review the evidence-backed notes below before making portfolio decisions.",
        "",
        "## Watchlist",
        "",
    ]
    if not stocks:
        lines.append("No active watchlist stocks found.")
    for stock in stocks:
        symbol = _field(stock, "symbol")
        name = _field(stock, "company_name") or symbol
        exchange = _field(stock, "exchange") or "N/A"
        sector = _field(stock, "sector") or "Unknown"
        priority = _field(stock, "priority")
        lines.append(f"- **{symbol}** ({exchange}): {name}; sector={sector}; priority={priority}")
    lines.extend(["", "## Short-Term Outliers", ""])
    for symbol, findings in price_findings.items():
        lines.append(f"### {symbol}")
        for finding in findings:
            lines.append(f"- {finding}")
    lines.extend(["", "## Recent Events", ""])
    for symbol, stock_events in events.items():
        lines.append(f"### {symbol}")
        if not stock_events:
            lines.append("- No recent web events captured.")
        for event in stock_events:
            source = f" [{event.get('source_name') or 'source'}]({event.get('source_url')})" if event.get("source_url") else ""
            lines.append(f"- **{event.get('impact', 'low')} / {event.get('sentiment', 'neutral')}**: {event.get('title')}{source}")
            if event.get("summary"):
                lines.append(f"  {event['summary'][:500]}")
    lines.extend(["", "## Diversification", ""])
    for note in diversification:
        lines.append(f"- {note}")
    lines.extend(
        [
            "",
            "## Action Ideas",
            "",
            "- Prioritize long-term thesis review before reacting to short-term moves.",
            "- Research further where negative catalysts repeat across multiple sources.",
            "- Treat large price/volume outliers as watch items unless confirmed by fundamentals and news.",
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


def _field(item: Any, name: str) -> Any:
    if isinstance(item, dict):
        return item.get(name)
    return getattr(item, name)
