from __future__ import annotations

from stonk_tracker_agent.db.session import SessionLocal
from stonk_tracker_agent.graph import run_report


def run_report_cli() -> None:
    with SessionLocal() as session:
        result = run_report(session)
        print(result.get("report_path", "Report run finished without a report path."))

