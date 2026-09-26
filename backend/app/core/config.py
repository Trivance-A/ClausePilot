from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/contract_ai"
    redis_url: str = "redis://localhost:6380/0"
    queue_async: bool = True  # False면 enqueue()가 워커 없이 호출 프로세스에서 즉시 동기 실행(테스트용, RQ 공식 지원 모드)
    jwt_secret: str = "dev-only-insecure-secret-change-me"
    storage_dir: str = str(Path(__file__).resolve().parents[2] / "storage")
    seed_demo_users: bool = True


settings = Settings()
