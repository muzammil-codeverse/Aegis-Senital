import sys
import os
import time

# Add project root to sys.path so `inference` package is importable
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from fastapi import FastAPI, HTTPException, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.api.routes import router
from app.api.security_dependencies import enforce_request_security
from app.models.database import init_db
from app.services.video_service import bootstrap_inference_runtime
from app.services.auth_service import get_auth_service
from app.core.logging_config import logger
from inference.logging_setup import configure_logging
from ml.runtime import system_boot_check
from app.services.websocket_alert_service import websocket_alert_service

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
    response = await enforce_request_security(request, call_next)
    elapsed_ms = (time.time() - start) * 1000
    logger.info(
        f"← {request.method} {request.url.path} {response.status_code} ({elapsed_ms:.1f}ms)"
    )
    return response


@app.exception_handler(HTTPException)
async def structured_http_exception(request: Request, exc: HTTPException):
    if isinstance(exc.detail, dict) and exc.detail.get("status"):
        content = exc.detail
    else:
        content = {"status": "error", "detail": exc.detail or "Request failed"}
    return JSONResponse(status_code=exc.status_code, content=content, headers=exc.headers)


app.include_router(router)


@app.websocket("/ws/alerts")
async def websocket_alerts(websocket: WebSocket):
    await websocket_alert_service.connect(websocket)


@app.on_event("startup")
async def startup():
    configure_logging()
    get_auth_service().bootstrap()
    system_boot_check()
    bootstrap_inference_runtime()
    init_db()
    # Initialize camera registry from config
    try:
        from app.services.camera_registry import get_camera_registry
        registry = get_camera_registry()
        snapshot = registry.snapshot()
        logger.info("Camera registry initialized: %s cameras", snapshot["total"])
    except Exception as exc:
        logger.warning("Camera registry init failed: %s", exc)
    logger.info("Aegis Sentinel startup complete.")


@app.get("/")
def root():
    return {"message": "Sentinel AI System is running"}
