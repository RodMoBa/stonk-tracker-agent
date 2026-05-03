"""Initial schema.

Revision ID: 0001_initial
Revises:
Create Date: 2026-05-03
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "watchlist_stocks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("exchange", sa.String(length=64), nullable=True),
        sa.Column("country_region", sa.String(length=64), nullable=True),
        sa.Column("currency", sa.String(length=16), nullable=True),
        sa.Column("company_name", sa.String(length=255), nullable=True),
        sa.Column("sector", sa.String(length=128), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("long_term_thesis", sa.Text(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("symbol", "exchange", name="uq_watchlist_symbol_exchange"),
    )
    op.create_index("ix_watchlist_active", "watchlist_stocks", ["active"])

    op.create_table(
        "price_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("stock_id", sa.Integer(), sa.ForeignKey("watchlist_stocks.id"), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("open_price", sa.Numeric(18, 4), nullable=True),
        sa.Column("high_price", sa.Numeric(18, 4), nullable=True),
        sa.Column("low_price", sa.Numeric(18, 4), nullable=True),
        sa.Column("close_price", sa.Numeric(18, 4), nullable=True),
        sa.Column("volume", sa.BigInteger(), nullable=True),
        sa.Column("market_cap", sa.Numeric(24, 2), nullable=True),
        sa.Column("pe_ratio", sa.Numeric(18, 4), nullable=True),
        sa.Column("dividend_yield", sa.Numeric(18, 6), nullable=True),
        sa.Column("raw_payload", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("stock_id", "snapshot_date", name="uq_price_stock_date"),
    )

    op.create_table(
        "stock_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("stock_id", sa.Integer(), sa.ForeignKey("watchlist_stocks.id"), nullable=False),
        sa.Column("event_date", sa.Date(), nullable=True),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("source_url", sa.String(length=1000), nullable=True),
        sa.Column("source_name", sa.String(length=255), nullable=True),
        sa.Column("sentiment", sa.String(length=32), nullable=True),
        sa.Column("impact", sa.String(length=32), nullable=True),
        sa.Column("raw_payload", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_stock_events_stock_date", "stock_events", ["stock_id", "event_date"])

    op.create_table(
        "reports",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("markdown_path", sa.String(length=1000), nullable=False),
        sa.Column("symbols_covered", sa.Text(), nullable=False),
        sa.Column("run_started_at", sa.DateTime(), nullable=False),
        sa.Column("run_finished_at", sa.DateTime(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "agent_threads",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("thread_id", sa.String(length=128), nullable=False, unique=True),
        sa.Column("purpose", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("agent_threads")
    op.drop_table("reports")
    op.drop_index("ix_stock_events_stock_date", table_name="stock_events")
    op.drop_table("stock_events")
    op.drop_table("price_snapshots")
    op.drop_index("ix_watchlist_active", table_name="watchlist_stocks")
    op.drop_table("watchlist_stocks")

