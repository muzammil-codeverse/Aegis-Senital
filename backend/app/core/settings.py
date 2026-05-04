import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from the backend/ directory (one level above app/)
_env_path = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(_env_path)

APP_ENV = os.getenv("APP_ENV", "dev")


def _require_postgres_url() -> str:
    dsn = os.getenv("DB_URL") or os.getenv("AEGIS_POSTGRES_DSN") or os.getenv("POSTGRES_DSN")
    if not dsn:
        raise RuntimeError("PostgreSQL is required for system operation")
    if not dsn.startswith(("postgres://", "postgresql://", "postgresql+asyncpg://", "postgresql+psycopg2://")):
        raise RuntimeError("PostgreSQL is required for system operation")
    return dsn


DB_URL = _require_postgres_url()
