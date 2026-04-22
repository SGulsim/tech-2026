from pydantic_settings import BaseSettings


class BotSettings(BaseSettings):
    telegram_bot_token: str
    backend_url: str = "http://backend:8000"
    rabbitmq_url: str = "amqp://guest:guest@rabbitmq:5672/"

    model_config = {"env_file": ".env", "extra": "ignore"}


bot_settings = BotSettings()
