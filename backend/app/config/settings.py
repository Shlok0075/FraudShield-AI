"""
FraudShield AI - Settings (PART 7, Week 7 Day 2)
==================================================
Reads all sensitive config from environment variables via
pydantic-settings. NEVER hardcode secrets (NFR6). See .env.example for
every variable this app expects.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- App ---
    APP_NAME: str = "FraudShield AI"
    ENVIRONMENT: str = "development"
    API_V1_PREFIX: str = "/api/v1"

    # --- Database ---
    DATABASE_URL: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/fraudshield"

    # --- Auth / JWT ---
    JWT_SECRET: str = "CHANGE_ME_IN_PRODUCTION_NEVER_COMMIT_REAL_SECRET"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60

    # --- CORS ---
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3000"

    # --- Rate limiting ---
    RATE_LIMIT_LOGIN: str = "10/minute"
    RATE_LIMIT_PREDICT: str = "60/minute"

    # --- ML ---
    ML_MODELS_DIR: str = "../ml/models"

    # --- Live feed ---
    # The built-in synthetic feed starts with the app so a signed-in dashboard
    # always has traffic to show. Set LIVE_FEED_ENABLED=false to turn it off
    # (e.g. when the real `scripts/simulator.py` is driving load instead, or in
    # production where synthetic transactions must not be injected at all).
    LIVE_FEED_ENABLED: bool = True
    LIVE_FEED_INTERVAL_SECONDS: float = 5.0
    LIVE_FEED_BURST: int = 3

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


settings = Settings()
