from __future__ import annotations

import pytest

from stonk_tracker_agent.config import Settings


SQL_ENV_VARS = ["MSSQL_SERVER", "DB_SERVER", "MSSQL_STONK_DB", "MSSQL_USER_WB", "MSSQL_PASSWORD", "MSSQL_PASSWORD_WB", "MSSQL_PASS_WB", "DATABASE_URL"]


@pytest.fixture
def clear_sql_env(monkeypatch):
    for name in SQL_ENV_VARS:
        monkeypatch.delenv(name, raising=False)


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

    assert url.startswith("mssql+pyodbc://?")
    assert "SERVER%3Dhost.docker.internal%2C1433" in url
    assert "DATABASE%3Dstonk_tracker" in url
    assert "UID%3Dsa" in url
    assert "PWD%3Dp%40ss%2Fword%3Awith%3Fchars" in url
    assert "TrustServerCertificate%3Dyes" in url
    assert "Encrypt%3Dyes" in url


def test_effective_database_url_falls_back_to_sqlite(clear_sql_env):
    assert Settings().effective_database_url == "sqlite:///./stonk_tracker_local.db"


def test_effective_database_url_uses_database_url_without_sql_server_settings(clear_sql_env):
    settings = Settings(database_url="sqlite:///custom.db")

    assert settings.effective_database_url == "sqlite:///custom.db"


def test_partial_sql_server_configuration_fails_loudly(clear_sql_env):
    settings = Settings(db_name="stonk_tracker", db_user="workbench-user")

    with pytest.raises(ValueError, match="MSSQL_SERVER"):
        _ = settings.effective_database_url


def test_mssql_environment_variable_names_are_supported(monkeypatch, clear_sql_env):
    monkeypatch.setenv("MSSQL_SERVER", "host.docker.internal")
    monkeypatch.setenv("MSSQL_STONK_DB", "stonk_tracker")
    monkeypatch.setenv("MSSQL_USER_WB", "workbench-user")

    settings = Settings()

    assert settings.db_name == "stonk_tracker"
    assert settings.db_user == "workbench-user"
    assert settings.db_password is None
    assert "SERVER%3Dhost.docker.internal%2C1433" in settings.effective_database_url
    assert "DATABASE%3Dstonk_tracker" in settings.effective_database_url
    assert "UID%3Dworkbench-user" in settings.effective_database_url
    assert "PWD%3Dworkbench-user" in settings.effective_database_url


def test_named_sql_server_instance_does_not_force_default_port():
    settings = Settings(db_server=r"RODPC\SQLEXPRESS", db_name="Stonks", db_user="etl_user")

    url = settings.effective_database_url

    assert "SERVER%3DRODPC%5CSQLEXPRESS" in url
    assert "SERVER%3DRODPC%5CSQLEXPRESS%2C1433" not in url


def test_mssql_password_environment_variable_overrides_username_password(monkeypatch, clear_sql_env):
    monkeypatch.setenv("MSSQL_SERVER", "host.docker.internal")
    monkeypatch.setenv("MSSQL_STONK_DB", "stonk_tracker")
    monkeypatch.setenv("MSSQL_USER_WB", "etl_user")
    monkeypatch.setenv("MSSQL_PASS_WB", "actual-password")

    settings = Settings()

    assert "UID%3Detl_user" in settings.effective_database_url
    assert "PWD%3Dactual-password" in settings.effective_database_url
