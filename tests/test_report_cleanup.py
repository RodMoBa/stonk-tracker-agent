from __future__ import annotations

from stonk_tracker_agent.reports import _clean_llm_summary


def test_clean_llm_summary_removes_nested_executive_summary_heading():
    assert _clean_llm_summary("## Executive Summary\n\nResearch text.") == "Research text."

