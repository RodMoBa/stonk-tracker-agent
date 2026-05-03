from __future__ import annotations

from datetime import date

from stonk_tracker_agent.db.repositories import ResearchRepository, WatchlistRepository


def test_watchlist_upsert_and_list_active(session):
    repo = WatchlistRepository(session)
    repo.upsert(symbol="msft", exchange="nasdaq", company_name="Microsoft", active=True)
    repo.upsert(symbol="sap", exchange="xetra", company_name="SAP", active=False)

    active = repo.list_active()

    assert [stock.symbol for stock in active] == ["MSFT"]


def test_save_price_snapshot_upserts_by_stock_and_date(session):
    stock = WatchlistRepository(session).upsert(symbol="MSFT", exchange="NASDAQ")
    repo = ResearchRepository(session)

    repo.save_price_snapshot(stock, {"snapshot_date": date(2026, 5, 1), "close_price": "100.00"})
    repo.save_price_snapshot(stock, {"snapshot_date": date(2026, 5, 1), "close_price": "101.00"})

    snapshots = repo.recent_snapshots(stock.id)
    assert len(snapshots) == 1
    assert str(snapshots[0].close_price) == "101.0000"

