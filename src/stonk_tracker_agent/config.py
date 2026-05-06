from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL


OPENAI_REPORT_MODEL_OPTIONS = [
    {
        "id": "gpt-5.4-nano",
        "label": "gpt-5.4-nano - low cost ($0.20 input / $1.25 output per 1M tokens)",
        "cost_note": "$0.20 input / $1.25 output per 1M tokens",
    },
    {
        "id": "gpt-5.4-mini",
        "label": "gpt-5.4-mini - balanced ($0.75 input / $4.50 output per 1M tokens)",
        "cost_note": "$0.75 input / $4.50 output per 1M tokens",
    },
    {
        "id": "gpt-5.4",
        "label": "gpt-5.4 - higher quality ($2.50 input / $15.00 output per 1M tokens)",
        "cost_note": "$2.50 input / $15.00 output per 1M tokens",
    },
    {
        "id": "gpt-5.5",
        "label": "gpt-5.5 - strongest non-pro option ($5.00 input / $30.00 output per 1M tokens)",
        "cost_note": "$5.00 input / $30.00 output per 1M tokens",
    },
]


class Settings(BaseSettings):
    database_url: str | None = None
    db_server: str | None = Field(default=None, validation_alias="MSSQL_SERVER")
    db_port: int = 1433
    db_name: str | None = Field(default=None, validation_alias="MSSQL_STONK_DB")
    db_user: str | None = Field(default=None, validation_alias="MSSQL_USER_WB")
    db_password: str | None = Field(default=None, validation_alias="MSSQL_PASS_WB")
    db_driver: str = "ODBC Driver 18 for SQL Server"
    db_trust_server_certificate: bool = True
    db_encrypt: bool = True
    sqlite_database_url: str = "sqlite:///./stonk_tracker_local.db"
    openai_api_key: str | None = None
    openai_model: str = "gpt-5.4-nano"
    alpha_vantage_api_key: str | None = None
    tavily_api_key: str | None = None
    reports_dir: Path = Field(default=Path("reports"))
    app_timezone: str = "Europe/Madrid"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore", populate_by_name=True)

    @property
    def effective_database_url(self) -> str:
        if self.db_server and self.db_name:
            server = self.db_server if "\\" in self.db_server else f"{self.db_server},{self.db_port}"
            odbc_parts = [
                f"DRIVER={{{self.db_driver}}}",
                f"SERVER={server}",
                f"DATABASE={self.db_name}",
                f"UID={self.db_user or ''}",
                f"PWD={self.db_password or self.db_user or ''}",
                f"TrustServerCertificate={'yes' if self.db_trust_server_certificate else 'no'}",
                f"Encrypt={'yes' if self.db_encrypt else 'no'}",
            ]
            return (
                URL.create(
                    "mssql+pyodbc",
                    query={"odbc_connect": ";".join(odbc_parts)},
                )
                .render_as_string(hide_password=False)
            )
        if self.db_server or self.db_name or self.db_user or self.db_password:
            missing = []
            if not self.db_server:
                missing.append("MSSQL_SERVER")
            if not self.db_name:
                missing.append("MSSQL_STONK_DB")
            raise ValueError(
                "Incomplete SQL Server configuration. "
                f"Missing: {', '.join(missing)}. "
                "Set all required SQL Server variables or clear them to use SQLite."
            )
        if self.database_url:
            return self.database_url
        return self.sqlite_database_url


@lru_cache
def get_settings() -> Settings:
    return Settings()
