from __future__ import annotations

from stonk_tracker_agent.reports import render_pdf_report


def test_render_pdf_report_returns_pdf_bytes():
    pdf = render_pdf_report(
        "\n".join(
            [
                "# Test Report",
                "",
                "## Disclaimer",
                "",
                "Research support only.",
                "",
                "| Action idea | Why it matters |",
                "| --- | --- |",
                "| Compare exposure | Identifies concentration |",
            ]
        )
    )

    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 500
