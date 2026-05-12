import os

from app.core.env_loader import load_project_env

load_project_env()

APP_ENV = os.getenv("APP_ENV", "dev")


def _require_postgres_url() -> str:
    dsn = os.getenv("DB_URL") or os.getenv("AEGIS_POSTGRES_DSN") or os.getenv("POSTGRES_DSN")
    if not dsn:
        raise RuntimeError("PostgreSQL is required for system operation")
    if not dsn.startswith(("postgres://", "postgresql://", "postgresql+asyncpg://", "postgresql+psycopg2://")):
        raise RuntimeError("PostgreSQL is required for system operation")
    return dsn


DB_URL = _require_postgres_url()
