# Stonk Tracker Agent

Local-first LangChain + LangGraph app for tracking a SQL-backed stock watchlist, collecting price/news context, and generating long-term-first portfolio research reports.

## What V1 Does

- Stores a watchlist, price snapshots, extracted events, reports, and chat threads in a relational database.
- Uses SQLAlchemy with SQL Server support through `mssql+pyodbc`.
- Fetches market data from Alpha Vantage when `ALPHA_VANTAGE_API_KEY` is configured.
- Searches recent stock news through Tavily when `TAVILY_API_KEY` is configured.
- Generates local markdown reports and records their metadata in the database.
- Provides a Streamlit app for watchlist editing, report runs, report reading, and agent chat.

The app is research support only. It does not place trades or give autonomous trading instructions.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

Set environment variables for your database and API keys. For SQL Server, prefer the split `DB_*` settings:

```powershell
$env:DB_SERVER="localhost"
$env:DB_PORT="1433"
$env:DB_NAME="stonk_tracker"
$env:DB_USER="sa"
$env:DB_PASSWORD="your-password"
```

If you do not set the required SQL Server `DB_*` settings or `DATABASE_URL`, the app uses `SQLITE_DATABASE_URL` so the app and tests can be explored before wiring SQL Server.

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
$env:DB_SERVER="host.docker.internal"
$env:DB_PORT="1433"
$env:DB_NAME="stonk_tracker"
$env:DB_USER="sa"
$env:DB_PASSWORD="your-password"
docker compose up --build
```

The container runs `alembic upgrade head` before starting Streamlit. By default, Docker uses SQLite with a named volume so you can test locally. For SQL Server, set `DB_SERVER` to a host reachable from inside the container, for example `host.docker.internal` for a SQL Server running on your host machine.

Set `RUN_MIGRATIONS=false` if you want to manage database migrations outside the container startup.

Run a report from the CLI:

```powershell
stonk-report
```

Run tests:

```powershell
pytest
```

## Environment

- `DATABASE_URL`: optional SQLAlchemy database URL override for non-standard cases. Split SQL Server `DB_*` settings take precedence when `DB_SERVER` and `DB_NAME` are set.
- `SQLITE_DATABASE_URL`: fallback SQLite URL, defaults locally to `sqlite:///./stonk_tracker_local.db` and in Docker to `sqlite:////data/stonk_tracker_local.db`.
- `DB_SERVER`: SQL Server host name, for example `localhost`, `host.docker.internal`, or a server DNS name.
- `DB_PORT`: SQL Server port, defaults to `1433`.
- `DB_NAME`: SQL Server database name.
- `DB_USER`: SQL Server username.
- `DB_PASSWORD`: SQL Server password.
- `DB_DRIVER`: ODBC driver, defaults to `ODBC Driver 18 for SQL Server`.
- `DB_TRUST_SERVER_CERTIFICATE`: defaults to `true`.
- `DB_ENCRYPT`: defaults to `true`.
- `OPENAI_API_KEY`: enables LLM-written report synthesis and chat answers.
- `OPENAI_MODEL`: defaults to `gpt-5.4-nano`.
- `ALPHA_VANTAGE_API_KEY`: enables market data ingestion.
- `TAVILY_API_KEY`: enables web-search ingestion.
- `REPORTS_DIR`: local markdown report directory.
