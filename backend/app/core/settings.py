import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from the backend/ directory (one level above app/)
_env_path = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(_env_path)

APP_ENV = os.getenv("APP_ENV", "dev")
DB_URL = os.getenv("DB_URL", "sqlite:///./sentinel.db")
