from typing import List
from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # App
    APP_NAME: str = "VOLTAGE"
    DEBUG: bool = False
    SECRET_KEY: str
    ALLOWED_ORIGINS: str = "http://localhost:3000"
    APP_AUTH_LOGIN: str = "admin"
    APP_AUTH_PASSWORD_HASH: str = ""
    APP_AUTH_COOKIE_SECURE: bool = True
    APP_AUTH_SESSION_TTL_HOURS: int = 24

    # Database
    DATABASE_URL: str

    # Redis
    REDIS_URL: str

    # Bybit
    BYBIT_API_KEY: str = ""
    BYBIT_API_SECRET: str = ""
    BYBIT_TESTNET: bool = False
    BYBIT_REQUEST_TIMEOUT: int = 20

    # DeepSeek AI
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com/v1"
    DEEPSEEK_MODEL: str = "deepseek-chat"

    # OpenAI / Codex OAuth
    OPENAI_CLIENT_ID: str = ""
    OPENAI_CLIENT_SECRET: str = ""
    OPENAI_REDIRECT_URI: str = ""

    # Trading defaults
    DEFAULT_PAPER_BALANCE: float = 10000.0
    DEFAULT_BACKTEST_BALANCE: float = 10000.0

    # Logging
    LOG_LEVEL: str = "INFO"

    # Runtime files
    ENV_FILE_PATH: str = "/run/config/voltage.env"

    @property
    def allowed_origins_list(self) -> List[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",")]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
