from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/contract_ai"
    jwt_secret: str = "dev-only-insecure-secret-change-me"
    storage_dir: str = str(Path(__file__).resolve().parents[2] / "storage")
    seed_demo_users: bool = True


settings = Settings()
