from __future__ import annotations

import os
import sys
import webbrowser
from pathlib import Path

from streamlit.web import cli as stcli


# In a packaged build, runtime files should live next to the exe; during local
# development they should live next to this launcher script.
def _runtime_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _bundle_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS"))
    return Path(__file__).resolve().parent


# This launcher hides the Streamlit CLI details and makes the app behave like a
# normal double-clickable desktop entrypoint.
def main() -> int:
    runtime_root = _runtime_root()
    bundle_root = _bundle_root()
    source_root = bundle_root / "src"
    app_path = bundle_root / "src" / "stonk_tracker_agent" / "streamlit_app.py"

    if not app_path.exists():
        raise FileNotFoundError(f"Could not find Streamlit app at {app_path}")
    if not source_root.exists():
        raise FileNotFoundError(f"Could not find source root at {source_root}")

    os.chdir(runtime_root)

    # Streamlit runs the target script in a different execution context, so we
    # explicitly seed both sys.path and PYTHONPATH with the bundled src tree.
    if str(source_root) not in sys.path:
        sys.path.insert(0, str(source_root))
    pythonpath_parts = [str(source_root)]
    existing_pythonpath = os.environ.get("PYTHONPATH")
    if existing_pythonpath:
        pythonpath_parts.append(existing_pythonpath)
    os.environ["PYTHONPATH"] = os.pathsep.join(pythonpath_parts)

    # Provide sensible local defaults so the packaged app can boot even before
    # someone wires SQL Server or external report storage.
    sqlite_path = runtime_root / "stonk_tracker_local.db"
    reports_path = runtime_root / "reports"
    os.environ.setdefault("SQLITE_DATABASE_URL", f"sqlite:///{sqlite_path.as_posix()}")
    os.environ.setdefault("REPORTS_DIR", str(reports_path))

    port = os.environ.get("STREAMLIT_SERVER_PORT", "8501")
    address = os.environ.get("STREAMLIT_SERVER_ADDRESS", "127.0.0.1")
    auto_open = os.environ.get("STREAMLIT_AUTO_OPEN_BROWSER", "true").lower() not in {"0", "false", "no"}

    # Delegate to Streamlit's CLI entrypoint instead of importing the app
    # module directly so behavior matches `streamlit run`.
    sys.argv = [
        "streamlit",
        "run",
        str(app_path),
        "--server.headless",
        "true",
        "--server.address",
        address,
        "--server.port",
        port,
        "--browser.gatherUsageStats",
        "false",
    ]

    if auto_open:
        webbrowser.open(f"http://{address}:{port}")

    return stcli.main()


if __name__ == "__main__":
    raise SystemExit(main())
