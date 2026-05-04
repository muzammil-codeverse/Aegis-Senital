import sys
import os
import time

# Add project root to sys.path so `inference` package is importable
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes import router
from app.models.database import init_db
from app.services.video_service import bootstrap_inference_runtime
from app.core.logging_config import logger
from inference.logging_setup import configure_logging
from ml.runtime import system_boot_check

app = FastAPI(title="Sentinel AI System", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.time()
    logger.info(f"→ {request.method} {request.url.path}")
    response = await call_next(request)
    elapsed_ms = (time.time() - start) * 1000
    logger.info(
        f"← {request.method} {request.url.path} {response.status_code} ({elapsed_ms:.1f}ms)"
    )
    return response


app.include_router(router)


@app.on_event("startup")
async def startup():
    configure_logging()
    system_boot_check()
    bootstrap_inference_runtime()
    init_db()
    logger.info("Aegis Sentinel startup complete.")


@app.get("/")
def root():
    return {"message": "Sentinel AI System is running"}
