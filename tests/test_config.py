from __future__ import annotations

from stonk_tracker_agent.config import Settings


def test_effective_database_url_prefers_complete_sql_server_settings():
    settings = Settings(database_url="sqlite:///custom.db", db_server="sql.example.com", db_name="stonk")

    assert settings.effective_database_url.startswith("mssql+pyodbc://")


def test_effective_database_url_builds_sql_server_url_with_escaped_password():
    settings = Settings(
        db_server="host.docker.internal",
        db_port=1433,
        db_name="stonk_tracker",
        db_user="sa",
        db_password="p@ss/word:with?chars",
    )

    url = settings.effective_database_url

    assert url.startswith("mssql+pyodbc://sa:")
    assert "host.docker.internal:1433/stonk_tracker" in url
    assert "driver=ODBC+Driver+18+for+SQL+Server" in url
    assert "TrustServerCertificate=yes" in url
    assert "Encrypt=yes" in url


def test_effective_database_url_falls_back_to_sqlite():
    assert Settings().effective_database_url == "sqlite:///./stonk_tracker_local.db"


def test_effective_database_url_uses_database_url_without_sql_server_settings():
    settings = Settings(database_url="sqlite:///custom.db")

    assert settings.effective_database_url == "sqlite:///custom.db"
