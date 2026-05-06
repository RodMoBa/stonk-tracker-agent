from __future__ import annotations

from stonk_tracker_agent.config import OPENAI_REPORT_MODEL_OPTIONS


def test_report_model_options_include_cost_tags_and_exclude_pro_models():
    model_ids = [item["id"] for item in OPENAI_REPORT_MODEL_OPTIONS]
    labels = [item["label"] for item in OPENAI_REPORT_MODEL_OPTIONS]

    assert "gpt-5.5" in model_ids
    assert "gpt-5.4" in model_ids
    assert "gpt-5.4-mini" in model_ids
    assert "gpt-5.4-nano" in model_ids
    assert all("pro" not in model_id.lower() for model_id in model_ids)
    assert all("per 1M tokens" in label for label in labels)
