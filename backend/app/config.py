from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    app_env: str = "development"
    secret_key: str = "dev-secret-key"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    mongo_uri: str = "mongodb://localhost:27017/"
    mongo_db_name: str = "slot_booking"

    pesu_auth_url: str = "https://pesuauth.example.com/api/login"

    frontend_origin: str = "http://localhost:5173"

    rate_limit_login: str = "5/minute"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache
def get_settings() -> Settings:
    return Settings()
