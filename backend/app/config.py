"""Application settings, read from environment variables (or a .env file)."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BACKEND_DIR / "data"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Supply Chain Forecasting API"
    database_url: str = f"sqlite:///{(BACKEND_DIR / 'forecasting.db').as_posix()}"
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    log_level: str = "INFO"

    # Seed demo data (synthetic sales + Excel context + festival calendar) when the DB is empty.
    seed_on_startup: bool = True
    seed_excel_path: Path = DATA_DIR / "dummy_data.xlsx"
    random_seed: int = 42

    # Forecasting defaults
    default_horizon_weeks: int = 12
    backtest_weeks: int = 52
    backtest_horizon: int = 4
    anomaly_z_threshold: float = 2.5

    # Local LLM (Ollama) used by the chat assistant. Everything else works without it.
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2"
    ollama_timeout_seconds: float = 300.0
    ollama_num_ctx: int = 4096


@lru_cache
def get_settings() -> Settings:
    return Settings()
