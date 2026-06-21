"""Logging configuration and HTTP request/response middleware.

Exposes two public symbols:
- ``setup_logging`` — call once at application startup to configure handlers,
  formatters, and the ``logs/app.log`` file output.
- ``RequestLoggingMiddleware`` — Starlette middleware that logs every incoming
  request and its response (status code, elapsed time).

``request_id`` is propagated to all log records within a request via a
``ContextVar`` and a ``logging.Filter``, so service and repository loggers
automatically include it without any code changes.
"""

import logging
import time
import uuid
from contextvars import ContextVar
from pathlib import Path
from typing import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(request_id)s | %(name)s | %(message)s"
_LOG_DATE_FORMAT = "%Y-%m-%dT%H:%M:%S"
_LOGS_DIR = Path("logs")
_LOG_FILE = _LOGS_DIR / "app.log"

# ---------------------------------------------------------------------------
# Request-ID context variable
# ---------------------------------------------------------------------------

_request_id_var: ContextVar[str] = ContextVar("request_id", default="-")


# ---------------------------------------------------------------------------
# Filter — injects request_id into every LogRecord
# ---------------------------------------------------------------------------


class _RequestIdFilter(logging.Filter):
    """Attach the current request_id from context to every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = _request_id_var.get()  # type: ignore[attr-defined]
        return True


# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------


def setup_logging(level: int = logging.INFO) -> None:
    """Configure the root logger with file and console handlers.

    Creates ``logs/app.log`` (and the ``logs/`` directory) automatically.
    Silences ``uvicorn.access`` to prevent duplicate per-request lines.

    Args:
        level: Logging level applied to the root logger. Defaults to INFO.
    """
    _LOGS_DIR.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter(_LOG_FORMAT, datefmt=_LOG_DATE_FORMAT)
    request_id_filter = _RequestIdFilter()

    file_handler = logging.FileHandler(_LOG_FILE, encoding="utf-8")
    file_handler.setFormatter(formatter)
    file_handler.addFilter(request_id_filter)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.addFilter(request_id_filter)

    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(file_handler)
    root.addHandler(console_handler)

    # Suppress uvicorn's built-in access log to avoid duplicate request lines.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log every HTTP request and its response to the configured logger.

    For each request:
    - Reads or generates a ``request_id`` (from ``X-Request-ID`` header).
    - Sets the ``_request_id_var`` ContextVar so all downstream loggers
      include the same ID automatically.
    - Logs the incoming method and path.
    - Logs the response status code and elapsed time in milliseconds.
    """

    _logger = logging.getLogger("app.middleware.request")

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        token = _request_id_var.set(request_id)
        start = time.perf_counter()

        self._logger.info(
            "Incoming %s %s",
            request.method,
            request.url.path,
        )

        try:
            response = await call_next(request)
        except Exception:
            elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
            self._logger.error(
                "Request error %s %s — %s ms",
                request.method,
                request.url.path,
                elapsed_ms,
                exc_info=True,
            )
            raise
        finally:
            _request_id_var.reset(token)

        elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
        self._logger.info(
            "Completed %s %s → %d in %s ms",
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
        )

        return response
