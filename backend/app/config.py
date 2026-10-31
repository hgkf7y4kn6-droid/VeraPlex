from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="VERAPLEX_", env_file=".env")

    database_url: str = "sqlite+pysqlite:///./dev.db"
    # Supabase JWT secret; the tenant comes from the verified token, never the request body.
    jwt_secret: str = "dev-only-change-me"
    jwt_audience: str = "authenticated"


settings = Settings()
