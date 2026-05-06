from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Protocol

import yfinance as yf

YAHOO_SUFFIX_CANDIDATES = ["", ".F", ".DE", ".MC", ".PA", ".AS", ".MI", ".L", ".SW", ".BR", ".LS", ".VI", ".ST", ".CO", ".HE", ".OL"]


class MarketDataProvider(Protocol):
    def get_history(self, symbol: str, days: int = 90) -> list[dict[str, Any]]:
        ...


class YFinanceMarketDataProvider:
    def get_profile(self, symbol: str) -> dict[str, Any]:
        resolved_symbol, info = self._resolve_info(symbol)
        return {
            "symbol": symbol,
            "resolved_symbol": resolved_symbol,
            "exchange": info.get("exchange") or info.get("fullExchangeName"),
            "country_region": info.get("country"),
            "currency": info.get("currency"),
            "company_name": info.get("longName") or info.get("shortName"),
            "sector": info.get("sector"),
            "industry": info.get("industry"),
            "long_business_summary": info.get("longBusinessSummary"),
            "raw_payload": info,
        }

    def get_history(self, symbol: str, days: int = 90) -> list[dict[str, Any]]:
        start = date.today() - timedelta(days=days)
        resolved_symbol, frame = self._resolve_history(symbol, start=start)
        if frame.empty:
            return []
        if hasattr(frame.columns, "nlevels") and frame.columns.nlevels > 1:
            frame.columns = frame.columns.get_level_values(0)
        rows: list[dict[str, Any]] = []
        for index, row in frame.iterrows():
            snapshot_date = index.date() if hasattr(index, "date") else date.fromisoformat(str(index)[:10])
            close_price = _clean_number(row.get("Close"))
            if close_price is None:
                continue
            rows.append(
                {
                    "snapshot_date": snapshot_date,
                    "open_price": _clean_number(row.get("Open")),
                    "high_price": _clean_number(row.get("High")),
                    "low_price": _clean_number(row.get("Low")),
                    "close_price": close_price,
                    "volume": int(row.get("Volume")) if row.get("Volume") == row.get("Volume") else None,
                    "raw_payload": {"provider": "yfinance", "symbol": symbol, "resolved_symbol": resolved_symbol},
                }
            )
        return rows

    def _resolve_info(self, symbol: str) -> tuple[str, dict[str, Any]]:
        last_info: dict[str, Any] = {}
        for candidate in yahoo_symbol_candidates(symbol):
            try:
                info = yf.Ticker(candidate).get_info()
            except Exception:
                continue
            last_info = info
            if _profile_has_identity(info):
                return candidate, info
        return symbol, last_info

    def _resolve_history(self, symbol: str, *, start: date):
        last_frame = None
        for candidate in yahoo_symbol_candidates(symbol):
            frame = yf.download(candidate, start=start.isoformat(), progress=False, auto_adjust=False, threads=False)
            last_frame = frame
            if not frame.empty:
                return candidate, frame
        return symbol, last_frame if last_frame is not None else yf.download(symbol, start=start.isoformat(), progress=False, auto_adjust=False, threads=False)


class NullMarketDataProvider:
    def get_profile(self, symbol: str) -> dict[str, Any]:
        return {"symbol": symbol}

    def get_history(self, symbol: str, days: int = 90) -> list[dict[str, Any]]:
        return []


def _clean_number(value: Any) -> float | None:
    if value is None or value != value:
        return None
    return float(value)


def yahoo_symbol_candidates(symbol: str) -> list[str]:
    normalized = symbol.strip().upper()
    if not normalized:
        return []
    if "." in normalized or "=" in normalized or "-" in normalized:
        return [normalized]
    return [f"{normalized}{suffix}" for suffix in YAHOO_SUFFIX_CANDIDATES]


def _profile_has_identity(info: dict[str, Any]) -> bool:
    return bool(info.get("longName") or info.get("shortName") or info.get("exchange") or info.get("currency"))
