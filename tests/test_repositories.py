from __future__ import annotations

from datetime import date

from sqlalchemy.dialects import mssql

from stonk_tracker_agent.db.repositories import ResearchRepository, WatchlistRepository, active_watchlist_statement


def test_watchlist_upsert_and_list_active(session):
    repo = WatchlistRepository(session)
    repo.upsert(symbol="msft", exchange="nasdaq", company_name="Microsoft", active=True)
    repo.upsert(symbol="sap", exchange="xetra", company_name="SAP", active=False)

    active = repo.list_active()

    assert [stock.symbol for stock in active] == ["MSFT"]


def test_watchlist_upsert_updates_existing_symbol_with_missing_exchange(session):
    repo = WatchlistRepository(session)
    original = repo.upsert(symbol="48CA", exchange=None, company_name="CAIXABANK", active=True)

    updated = repo.upsert(symbol="48CA", exchange="FRA", company_name="CaixaBank, S.A.", active=True)

    assert updated.id == original.id
    assert updated.exchange == "FRA"
    assert len(repo.list_all()) == 1


def test_active_watchlist_query_compiles_for_sql_server_without_is_one():
    compiled = str(active_watchlist_statement().compile(dialect=mssql.dialect(), compile_kwargs={"literal_binds": True}))

    assert " IS 1" not in compiled
    assert "active = 1" in compiled


def test_save_price_snapshot_upserts_by_stock_and_date(session):
    stock = WatchlistRepository(session).upsert(symbol="MSFT", exchange="NASDAQ")
    repo = ResearchRepository(session)

    repo.save_price_snapshot(stock, {"snapshot_date": date(2026, 5, 1), "close_price": "100.00"})
    repo.save_price_snapshot(stock, {"snapshot_date": date(2026, 5, 1), "close_price": "101.00"})

    snapshots = repo.recent_snapshots(stock.id)
    assert len(snapshots) == 1
    assert str(snapshots[0].close_price) == "101.0000"


def test_save_event_deduplicates_by_source_url(session):
    stock = WatchlistRepository(session).upsert(symbol="MSFT", exchange="NASDAQ")
    repo = ResearchRepository(session)

    repo.save_event(
        stock,
        {
            "event_date": date(2026, 5, 1),
            "title": "Old title",
            "summary": "Initial story",
            "source_url": "https://example.com/msft",
        },
    )
    repo.save_event(
        stock,
        {
            "event_date": date(2026, 5, 2),
            "title": "Updated title",
            "summary": "Updated story",
            "source_url": "https://example.com/msft",
        },
    )

    events = repo.recent_events(stock.id)
    assert len(events) == 1
    assert events[0].title == "Updated title"
