from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="VERAPLEX_", env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./veraplex.db"
    supabase_jwt_secret: str = "dev-only-secret-change-me-32-bytes-min!"
    jwt_audience: str = "authenticated"
    reauth_max_age_seconds: int = 120
    recurrence_window_days: int = 90
    recurrence_threshold: int = 3
    effectiveness_check_days: int = 90


settings = Settings()
