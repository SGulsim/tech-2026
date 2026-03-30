from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://dating_user:dating_pass@postgres:5432/dating_db"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
