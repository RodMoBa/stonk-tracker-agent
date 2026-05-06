from __future__ import annotations

from stonk_tracker_agent.providers.search import _is_relevant_result


def test_relevance_filter_accepts_symbol_or_company_name():
    assert _is_relevant_result({"title": "MSFT rises after earnings"}, symbol="MSFT", company_name="Microsoft")
    assert _is_relevant_result({"title": "Microsoft Azure growth accelerates"}, symbol="MSFT", company_name="Microsoft")


def test_relevance_filter_rejects_unrelated_news():
    assert not _is_relevant_result({"title": "Waters announces FDA clearance"}, symbol="MSFT", company_name="Microsoft")

