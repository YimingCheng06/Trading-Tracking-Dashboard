from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Trading Dashboard"
    environment: str = "local"
    database_url: str = "sqlite:///./data/app.db"
    base_currency: str = "USD"
    cors_origins: list[str] = ["http://localhost:3000"]
    ibkr_gateway_url: str = "https://localhost:5000/v1/api"
    ibkr_gateway_timeout_seconds: float = 2.0

    @property
    def data_dir(self) -> Path:
        path = Path(__file__).resolve().parents[2] / "data"
        path.mkdir(exist_ok=True)
        return path


settings = Settings()
