"""SurveyPro application configuration (12-factor, environment driven)."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import List, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings.

    ``DATABASE_URL`` accepts an async URL.  PostgreSQL + PostGIS is the production
    target (``postgresql+asyncpg://...``); SQLite (``sqlite+aiosqlite:///...``) is the
    zero-dependency developer/demo fallback and stores geometry as ISO WKT.
    """

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"), env_file_encoding="utf-8", extra="ignore",
        env_prefix="SURVEYPRO_",
    )

    app_name: str = "SurveyPro"
    environment: Literal["development", "production", "test"] = "development"
    debug: bool = True
    api_prefix: str = "/api/v1"

    database_url: str = "sqlite+aiosqlite:///./data/surveypro.db"
    db_echo: bool = False
    db_pool_size: int = 10
    db_max_overflow: int = 20

    upload_dir: Path = Path("./data/uploads")
    max_upload_bytes: int = 64 * 1024 * 1024

    cors_origins: List[str] = Field(default_factory=lambda: ["*"])

    # default surveying parameters (a Project may override each of them)
    default_crs_epsg: int = 28992            # RD New / Amersfoort -- Dutch national grid
    default_vertical_datum: str = "NAP"
    default_angle_unit: str = "gon"          # Leica factory setting
    default_duplicate_xy_tolerance: float = 0.005
    default_duplicate_z_tolerance: float = 0.02
    default_z_mad_threshold: float = 3.5
    default_tin_boundary_mode: str = "concave_hull"
    default_contour_interval: float = 0.10
    default_breakline_codes: List[str] = Field(
        default_factory=lambda: ["KBL", "KBR", "KBBL", "KBBR", "BRK", "CURB", "KB", "EDGE"]
    )
    sample_data_dir: Path = Path("../sample_data")

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value):
        if isinstance(value, str):
            if value.strip() == "*":
                return ["*"]
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @property
    def is_postgres(self) -> bool:
        return self.database_url.startswith("postgresql")

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    def ensure_directories(self) -> None:
        Path(self.upload_dir).mkdir(parents=True, exist_ok=True)
        if self.is_sqlite:
            db_path = self.database_url.split("///")[-1]
            parent = Path(db_path).parent
            if str(parent) not in ("", "."):
                parent.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_directories()
    return settings


settings = get_settings()

# Allow tests / containers to override the sample data location without a rebuild.
if os.environ.get("SURVEYPRO_SAMPLE_DATA_DIR"):
    settings.sample_data_dir = Path(os.environ["SURVEYPRO_SAMPLE_DATA_DIR"])
