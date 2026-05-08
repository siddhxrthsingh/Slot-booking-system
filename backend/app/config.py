from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    app_env: str = "development"
    secret_key: str = "dev-secret-key"
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 1  # session-only: 1 day max

    mongo_uri: str = "mongodb://localhost:27017/"
    mongo_db_name: str = "slot_booking"

    pesu_auth_url: str = "https://pesu-auth.onrender.com/authenticate"

    frontend_origin: str = "http://localhost:5173"

    rate_limit_login: str = "10/minute"

    # Admin credentials (employee-ID based, no external API)
    admin_employee_id: str = "EMP001"
    admin_password: str = "admin123"
    admin_name: str = "Sports Admin"
    admin_email: str = "admin@pesu.edu"

    # Email notifications (optional — leave blank to disable)
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "noreply@pesu.edu"

    # Booking policy
    cancel_window_hours: int = 2   # must cancel at least N hours before slot
    ban_duration_days: int = 2     # late-cancel penalty ban duration

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache
def get_settings() -> Settings:
    return Settings()
