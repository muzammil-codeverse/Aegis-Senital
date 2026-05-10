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
from app.api.websocket_security import authenticate_websocket
from app.services.auth_service import get_auth_service
from app.security.config import get_auth_config
from app.core.logging_config import logger
from inference.logging_setup import configure_logging
from ml.runtime import system_boot_check
from app.services.websocket_alert_service import websocket_alert_service


_DEFAULT_CORS_ORIGINS = (
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://[::1]:5173",
    "http://localhost:4173",
    "http://127.0.0.1:4173",
    "http://[::1]:4173",
)


def _get_allowed_cors_origins() -> list[str]:
    raw_value = os.getenv("CORS_ALLOW_ORIGINS", "")
    if not raw_value.strip():
        return list(_DEFAULT_CORS_ORIGINS)
    return [origin.strip() for origin in raw_value.split(",") if origin.strip()]


app = FastAPI(title="Sentinel AI System", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_get_allowed_cors_origins(),
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1|\[::1\])(?::\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.time()
    logger.info("-> %s %s", request.method, request.url.path)
    response = await enforce_request_security(request, call_next)
    elapsed_ms = (time.time() - start) * 1000
    logger.info(
        "<- %s %s %s (%.1fms)",
        request.method,
        request.url.path,
        response.status_code,
        elapsed_ms,
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
    user = await authenticate_websocket(websocket, required_permission="alert:read")
    if user is None:
        return
    await websocket_alert_service.connect(websocket, user=user)


@app.on_event("startup")
async def startup():
    from app.models.database import init_db
    from app.services.case_service import get_case_service
    from app.services.llm_service import get_llm_service
    from app.services.video_service import bootstrap_inference_runtime

    configure_logging()
    auth_cfg = get_auth_config()
    if (os.getenv("APP_ENV") or "").lower() in {"prod", "production"} and not bool(auth_cfg.get("cookie_secure", False)):
        logger.warning("APP_ENV=prod with auth.cookie_secure=false; set cookie_secure=true behind HTTPS")
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
    try:
        get_case_service()
    except Exception as exc:
        logger.warning("Case service init failed: %s", exc)
    try:
        get_llm_service()
    except Exception as exc:
        logger.warning("LLM service init failed: %s", exc)
    logger.info("Aegis Sentinel startup complete.")


@app.get("/")
def root():
    return {"message": "Sentinel AI System is running"}
