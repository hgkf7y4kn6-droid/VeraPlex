from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="VERAPLEX_", env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./veraplex.db"
    environment: str = "development"
    supabase_url: str | None = None  # e.g. https://<ref>.supabase.co ; enables JWKS verification
    supabase_service_key: str | None = None  # server-side only; used for the Admin API (invites)
    supabase_jwt_secret: str | None = "dev-only-secret-change-me-32-bytes-min!"  # legacy HS256; set to None in production
    jwt_audience: str = "authenticated"
    reauth_max_age_seconds: int = 120
    recurrence_window_days: int = 90
    recurrence_threshold: int = 3
    effectiveness_check_days: int = 90
    training_due_days: int = 14
    # Retrieval
    embedding_url: str | None = None  # text-embeddings-inference base URL; unset -> local hashing embedder
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    # Generation. External inference is off per tenant unless an administrator opts in.
    anthropic_api_key: str | None = None  # falls back to ANTHROPIC_API_KEY in the SDK when unset
    ai_model: str = "claude-opus-5-5"
    ai_effort: str = "medium"
    ai_max_output_tokens: int = 8000
    ai_daily_token_budget: int = 2_000_000
    ai_input_usd_per_mtok: float = 4.0  # price table cached 2026-10-06; confirm before billing customers
    ai_output_usd_per_mtok: float = 20.0


settings = Settings()


DEV_SECRET = "dev-only-secret-change-me-32-bytes-min!"


def assert_production_safe(s: Settings = settings) -> None:
    if s.environment == "production":
        if s.supabase_jwt_secret == DEV_SECRET:
            raise RuntimeError("refusing to start: default dev JWT secret in production")
        if not s.supabase_url:
            raise RuntimeError("refusing to start: VERAPLEX_SUPABASE_URL (JWKS) is required in production")
