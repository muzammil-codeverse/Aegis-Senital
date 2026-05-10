from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from app.api.analytics_routes import router as analytics_router
from app.api.security_dependencies import enforce_request_security
from app.models.security_models import UserAccount


def make_user(role: str) -> UserAccount:
    return UserAccount(
        user_id=f"user-{role}",
        username=role,
        display_name=role,
        role=role,
        status="active",
        password_hash="hash",
        created_at=1.0,
        updated_at=1.0,
    )


def build_analytics_test_app() -> FastAPI:
    app = FastAPI()

    @app.middleware("http")
    async def security_middleware(request: Request, call_next):
        return await enforce_request_security(request, call_next)

    @app.exception_handler(HTTPException)
    async def structured_http_exception(request: Request, exc: HTTPException):
        del request
        if isinstance(exc.detail, dict) and exc.detail.get("status"):
            content = exc.detail
        else:
            content = {"status": "error", "detail": exc.detail or "Request failed"}
        return JSONResponse(status_code=exc.status_code, content=content, headers=exc.headers)

    app.include_router(analytics_router)
    return app
