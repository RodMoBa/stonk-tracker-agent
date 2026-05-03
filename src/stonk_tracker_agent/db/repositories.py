from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from stonk_tracker_agent.db.models import AgentThread, PriceSnapshot, Report, StockEvent, WatchlistStock


def _decimal(value: Any) -> Decimal | None:
    if value in (None, "", "None"):
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


class WatchlistRepository:
    def __init__(self, session: Session):
        self.session = session

    def list_active(self) -> list[WatchlistStock]:
        return list(self.session.scalars(select(WatchlistStock).where(WatchlistStock.active.is_(True)).order_by(WatchlistStock.symbol)))

    def list_all(self) -> list[WatchlistStock]:
        return list(self.session.scalars(select(WatchlistStock).order_by(WatchlistStock.symbol)))

    def upsert(
        self,
        *,
        symbol: str,
        exchange: str | None = None,
        country_region: str | None = None,
        currency: str | None = None,
        company_name: str | None = None,
        sector: str | None = None,
        priority: int = 3,
        long_term_thesis: str | None = None,
        active: bool = True,
    ) -> WatchlistStock:
        normalized_symbol = symbol.strip().upper()
        normalized_exchange = exchange.strip().upper() if exchange else None
        stock = self.session.scalar(
            select(WatchlistStock).where(
                WatchlistStock.symbol == normalized_symbol,
                WatchlistStock.exchange == normalized_exchange,
            )
        )
        if stock is None:
            stock = WatchlistStock(symbol=normalized_symbol, exchange=normalized_exchange)
            self.session.add(stock)
        stock.country_region = country_region
        stock.currency = currency
        stock.company_name = company_name
        stock.sector = sector
        stock.priority = priority
        stock.long_term_thesis = long_term_thesis
        stock.active = active
        self.session.commit()
        return stock

    def deactivate(self, stock_id: int) -> None:
        stock = self.session.get(WatchlistStock, stock_id)
        if stock:
            stock.active = False
            self.session.commit()


class ResearchRepository:
    def __init__(self, session: Session):
        self.session = session

    def save_price_snapshot(self, stock: WatchlistStock, snapshot: dict[str, Any]) -> PriceSnapshot:
        snapshot_date = snapshot.get("snapshot_date") or date.today()
        existing = self.session.scalar(
            select(PriceSnapshot).where(
                PriceSnapshot.stock_id == stock.id,
                PriceSnapshot.snapshot_date == snapshot_date,
            )
        )
        item = existing or PriceSnapshot(stock_id=stock.id, snapshot_date=snapshot_date)
        item.open_price = _decimal(snapshot.get("open_price"))
        item.high_price = _decimal(snapshot.get("high_price"))
        item.low_price = _decimal(snapshot.get("low_price"))
        item.close_price = _decimal(snapshot.get("close_price"))
        item.volume = snapshot.get("volume")
        item.market_cap = _decimal(snapshot.get("market_cap"))
        item.pe_ratio = _decimal(snapshot.get("pe_ratio"))
        item.dividend_yield = _decimal(snapshot.get("dividend_yield"))
        item.raw_payload = json.dumps(snapshot.get("raw_payload", {}), default=str)
        self.session.add(item)
        self.session.commit()
        return item

    def save_event(self, stock: WatchlistStock, event: dict[str, Any]) -> StockEvent:
        item = StockEvent(
            stock_id=stock.id,
            event_date=event.get("event_date"),
            title=event.get("title") or "Untitled event",
            summary=event.get("summary"),
            source_url=event.get("source_url"),
            source_name=event.get("source_name"),
            sentiment=event.get("sentiment"),
            impact=event.get("impact"),
            raw_payload=json.dumps(event.get("raw_payload", {}), default=str),
        )
        self.session.add(item)
        self.session.commit()
        return item

    def recent_snapshots(self, stock_id: int, limit: int = 10) -> list[PriceSnapshot]:
        stmt = select(PriceSnapshot).where(PriceSnapshot.stock_id == stock_id).order_by(desc(PriceSnapshot.snapshot_date)).limit(limit)
        return list(self.session.scalars(stmt))

    def recent_events(self, stock_id: int, limit: int = 10) -> list[StockEvent]:
        stmt = select(StockEvent).where(StockEvent.stock_id == stock_id).order_by(desc(StockEvent.created_at)).limit(limit)
        return list(self.session.scalars(stmt))

    def save_report(
        self,
        *,
        title: str,
        markdown_path: Path,
        symbols_covered: list[str],
        run_started_at: datetime,
        run_finished_at: datetime,
        summary: str | None,
    ) -> Report:
        report = Report(
            title=title,
            markdown_path=str(markdown_path),
            symbols_covered=json.dumps(symbols_covered),
            run_started_at=run_started_at,
            run_finished_at=run_finished_at,
            summary=summary,
        )
        self.session.add(report)
        self.session.commit()
        return report

    def list_reports(self, limit: int = 50) -> list[Report]:
        stmt = select(Report).order_by(desc(Report.run_finished_at)).limit(limit)
        return list(self.session.scalars(stmt))


class AgentThreadRepository:
    def __init__(self, session: Session):
        self.session = session

    def ensure(self, *, thread_id: str, purpose: str, title: str | None = None) -> AgentThread:
        thread = self.session.scalar(select(AgentThread).where(AgentThread.thread_id == thread_id))
        if thread is None:
            thread = AgentThread(thread_id=thread_id, purpose=purpose, title=title)
            self.session.add(thread)
            self.session.commit()
        return thread

