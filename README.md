# Stonk Tracker Agent

Local-first LangChain + LangGraph app for tracking a SQL-backed stock watchlist, collecting price/news context, and generating long-term-first portfolio research reports.

## What V1 Does

- Stores a watchlist, price snapshots, extracted events, reports, and chat threads in a relational database.
- Uses SQLAlchemy with SQL Server support through `mssql+pyodbc`.
- Fetches daily historical prices from yfinance and stores them as per-stock price history.
- Searches recent 30-day stock news through Tavily when `TAVILY_API_KEY` is configured, deduplicates it, and keeps a historic event record.
- Generates local markdown reports and records their metadata in the database.
- Exports saved reports to PDF from the Streamlit Reports tab.
- Provides a Streamlit app for watchlist editing, report runs, report reading, and agent chat.
- Enriches new watchlist entries before saving by generating exchange, country, sector, recent event history, recent price history, and a long-term thesis.

The app is research support only. It does not place trades or give autonomous trading instructions.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

Set environment variables for your database and API keys. For SQL Server, prefer the split `DB_*` settings:

```powershell
$env:MSSQL_SERVER="localhost"
$env:DB_PORT="1433"
$env:MSSQL_STONK_DB="stonk_tracker"
$env:MSSQL_USER_WB="sa"
$env:MSSQL_PASS_WB="your-password"
```

If you do not set the required SQL Server settings or `DATABASE_URL`, the app uses `SQLITE_DATABASE_URL` so the app and tests can be explored before wiring SQL Server.

If any SQL Server split variable is set, `MSSQL_SERVER` and `MSSQL_STONK_DB` are both required. The app fails fast instead of silently writing to SQLite when SQL Server config is incomplete.

For local Python development, you may also copy `.env.example` to `.env`; the app reads it as a convenience. Environment variables still take precedence over `.env` values.

Run migrations:

```powershell
alembic upgrade head
```

Start the app:

```powershell
streamlit run src/stonk_tracker_agent/streamlit_app.py
```

## Docker

Build and run the Streamlit app in a container:

```powershell
docker build -t stonk-tracker-agent:local .
docker run --rm -p 8501:8501 `
  -e OPENAI_API_KEY=$env:OPENAI_API_KEY `
  -e ALPHA_VANTAGE_API_KEY=$env:ALPHA_VANTAGE_API_KEY `
  -e TAVILY_API_KEY=$env:TAVILY_API_KEY `
  -v stonk-data:/data `
  -v stonk-reports:/app/reports `
  stonk-tracker-agent:local
```

Or use Compose:

```powershell
docker compose up --build
```

Compose reads variables from your shell environment and passes them into the container. Example:

```powershell
$env:OPENAI_API_KEY="..."
$env:ALPHA_VANTAGE_API_KEY="..."
$env:TAVILY_API_KEY="..."
$env:MSSQL_SERVER="host.docker.internal"
$env:DB_PORT="1433"
$env:MSSQL_STONK_DB="stonk_tracker"
$env:MSSQL_USER_WB="sa"
$env:MSSQL_PASS_WB="your-password"
docker compose up --build
```

The container runs `alembic upgrade head` before starting Streamlit. By default, Docker uses SQLite with a named volume so you can test locally. For SQL Server, set `MSSQL_SERVER` to a host reachable from inside the container, for example `host.docker.internal` for a SQL Server running on your host machine.

Set `RUN_MIGRATIONS=false` if you want to manage database migrations outside the container startup.

Run a report from the CLI:

```powershell
stonk-report
```

Run tests:

```powershell
pytest
```

## Windows EXE Build

Build a double-clickable Windows launcher with PyInstaller:

```powershell
pip install pyinstaller
pyinstaller StonkTracker.spec --clean
```

The packaged app will be created at:

```text
dist\StonkTracker.exe
```

When launched, the exe starts Streamlit for this app and writes its default local files next to the exe:

- `stonk_tracker_local.db`
- `reports\`

The exe still reads environment variables such as `OPENAI_API_KEY`, `TAVILY_API_KEY`, `MSSQL_SERVER`, `MSSQL_STONK_DB`, `MSSQL_USER_WB`, and `MSSQL_PASS_WB` if you want OpenAI, Tavily, or SQL Server enabled.

## Environment

- `DATABASE_URL`: optional SQLAlchemy database URL override for non-standard cases. Split SQL Server settings take precedence when `MSSQL_SERVER` and `MSSQL_STONK_DB` are set.
- `SQLITE_DATABASE_URL`: fallback SQLite URL, defaults locally to `sqlite:///./stonk_tracker_local.db` and in Docker to `sqlite:////data/stonk_tracker_local.db`.
- `MSSQL_SERVER`: SQL Server host name, for example `localhost`, `host.docker.internal`, or a server DNS name.
- `DB_PORT`: SQL Server port, defaults to `1433`.
- `MSSQL_STONK_DB`: SQL Server database name.
- `MSSQL_USER_WB`: SQL Server username.
- `MSSQL_PASS_WB`: optional SQL Server password. If omitted, the app falls back to using `MSSQL_USER_WB` as the password for backward compatibility.
- `DB_DRIVER`: ODBC driver, defaults to `ODBC Driver 18 for SQL Server`.
- `DB_TRUST_SERVER_CERTIFICATE`: defaults to `true`.
- `DB_ENCRYPT`: defaults to `true`.
- `OPENAI_API_KEY`: enables LLM-written report synthesis and chat answers.
- `OPENAI_MODEL`: defaults to `gpt-5.4-nano`. The Run Report tab also lets you choose `gpt-5.4-nano`, `gpt-5.4-mini`, `gpt-5.4`, or `gpt-5.5` with cost tags; pro models are excluded.
- `ALPHA_VANTAGE_API_KEY`: reserved for future provider extensions; current price ingestion uses yfinance.
- `TAVILY_API_KEY`: enables web-search ingestion.
- `REPORTS_DIR`: local markdown report directory.
