from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Trading Dashboard"
    environment: str = "local"
    database_url: str = "sqlite:///./data/app.db"
    base_currency: str = "USD"
    cors_origins: list[str] = ["http://localhost:3000"]

    @property
    def data_dir(self) -> Path:
        path = Path(__file__).resolve().parents[2] / "data"
        path.mkdir(exist_ok=True)
        return path


settings = Settings()
