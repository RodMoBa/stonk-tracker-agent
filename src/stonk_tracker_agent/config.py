from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL


class Settings(BaseSettings):
    database_url: str | None = None
    db_server: str | None = None
    db_port: int = 1433
    db_name: str | None = None
    db_user: str | None = None
    db_password: str | None = None
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

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def effective_database_url(self) -> str:
        if self.db_server and self.db_name:
            query = {
                "driver": self.db_driver,
                "TrustServerCertificate": "yes" if self.db_trust_server_certificate else "no",
                "Encrypt": "yes" if self.db_encrypt else "no",
            }
            return str(
                URL.create(
                    "mssql+pyodbc",
                    username=self.db_user,
                    password=self.db_password,
                    host=self.db_server,
                    port=self.db_port,
                    database=self.db_name,
                    query=query,
                )
            )
        if self.database_url:
            return self.database_url
        return self.sqlite_database_url


@lru_cache
def get_settings() -> Settings:
    return Settings()
