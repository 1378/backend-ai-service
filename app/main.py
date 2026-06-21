"""FastAPI application — bootstrap and dependency wiring only.

No business logic lives here. This module is responsible solely for:
- Creating the FastAPI app instance
- Wiring all service dependencies via lifespan
- Registering middleware and routers
- Providing a global exception handler
"""

import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import get_contact_service, get_metrics_service, router
from app.config import settings
from app.middleware.logger import RequestLoggingMiddleware, setup_logging
from app.repositories.log_repository import LogRepository
from app.repositories.rate_limit_repository import RateLimitRepository
from app.services.ai_service import AIService
from app.services.contact_service import ContactService
from app.services.email_service import EmailService
from app.services.metrics_service import MetricsService

setup_logging()

logger = logging.getLogger(__name__)


class _ServiceLogger:
    """Thin adapter making stdlib logging compatible with LoggerProtocol.

    ContactService uses structured keyword arguments (e.g. request_id=...).
    Stdlib Logger accepts them only via the ``extra`` dict, so this wrapper
    translates the call signature accordingly.
    """

    def __init__(self, name: str) -> None:
        self._log = logging.getLogger(name)

    def info(self, message: str, **kwargs: Any) -> None:
        self._log.info(message, extra=kwargs)

    def warning(self, message: str, **kwargs: Any) -> None:
        self._log.warning(message, extra=kwargs)

    def error(self, message: str, **kwargs: Any) -> None:
        self._log.error(message, extra=kwargs)


# ---------------------------------------------------------------------------
# Lifespan — instantiate and wire all dependencies before the app starts
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Wire service dependencies and register FastAPI dependency overrides."""
    rate_limit_repo = RateLimitRepository()
    log_repository = LogRepository()
    ai_service = AIService()
    email_service = EmailService()
    metrics_service = MetricsService()
    contact_service = ContactService(
        ai_service=ai_service,
        email_service=email_service,
        log_repository=log_repository,
        metrics_service=metrics_service,
        rate_limit_service=rate_limit_repo,
        logger=_ServiceLogger("app.services.contact_service"),
    )
    app.dependency_overrides[get_contact_service] = lambda: contact_service
    app.dependency_overrides[get_metrics_service] = lambda: metrics_service

    logger.info("Application startup complete")
    health = SystemHealthService()

    openai_ok = await health.check_openai()
    ollama_ok = await health.check_ollama()
    smtp_ok = health.check_smtp()
    health.print_report(openai_ok, ollama_ok, smtp_ok)
    yield

    app.dependency_overrides.clear()
    logger.info("Application shutdown complete")


# ---------------------------------------------------------------------------
# Application instance
# ---------------------------------------------------------------------------

app = FastAPI(
    title=settings.APP_NAME,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict to specific origins in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

app.include_router(router, prefix=settings.API_PREFIX)

# ---------------------------------------------------------------------------
# Global exception handler
# ---------------------------------------------------------------------------


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch unhandled exceptions and return a safe, generic error response."""
    logger.error(
        "Unhandled exception: %s %s",
        request.method,
        request.url,
        exc_info=True,
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error"},
    )


# ---------------------------------------------------------------------------
# Uvicorn entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
from app.services.system_health import SystemHealthService