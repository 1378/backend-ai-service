"""File-based rate limiting using a sliding time window."""

import json
import logging
import os
import threading
import time
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)

_file_lock = threading.Lock()

_RateLimitData = dict[str, list[float]]


class RateLimitExceededError(Exception):
    """Raised when a client key exceeds the configured request rate."""


class RateLimitRepository:
    """Tracks request timestamps per client key in a local JSON file.

    Uses a sliding window: only requests within the last ``window_seconds``
    count toward the limit.  All storage failures follow a fail-open strategy
    so that a broken file never blocks legitimate traffic.

    Thread safety is provided by a module-level :class:`threading.Lock` that
    covers the load → check → save cycle.  Writes are atomic via a temporary
    file and :func:`os.replace`.
    """

    def __init__(
        self,
        storage_path: Path = Path("data/rate_limit.json"),
        max_requests: int = settings.RATE_LIMIT_REQUESTS,
        window_seconds: int = settings.RATE_LIMIT_WINDOW,
    ) -> None:
        self._path = Path(storage_path)
        self._max_requests = max_requests
        self._window_seconds = window_seconds

    async def check_rate_limit(self, client_key: str) -> None:
        """Enforce the sliding-window rate limit for ``client_key``.

        Raises:
            RateLimitExceededError: when the client has exceeded the limit.

        On any storage failure the error is logged and the request is allowed
        through (fail-open).
        """
        with _file_lock:
            try:
                self._check_and_record(client_key)
            except RateLimitExceededError:
                raise
            except Exception:
                logger.error(
                    "Rate limit storage error for client %r — allowing request",
                    client_key,
                    exc_info=True,
                )

    def _check_and_record(self, client_key: str) -> None:
        """Load data, enforce the limit, append the timestamp, and persist."""
        data = self._load()
        now = time.time()
        cutoff = now - self._window_seconds

        timestamps = [ts for ts in data.get(client_key, []) if ts > cutoff]

        if len(timestamps) >= self._max_requests:
            raise RateLimitExceededError(
                f"Rate limit exceeded for {client_key!r}: "
                f"{self._max_requests} requests per {self._window_seconds}s window"
            )

        timestamps.append(now)
        data[client_key] = timestamps
        self._save(data)

    def _load(self) -> _RateLimitData:
        """Read rate limit data from the JSON file.

        Returns an empty dict when the file does not exist yet or contains
        unexpected data.
        """
        if not self._path.exists():
            return {}

        with self._path.open("r", encoding="utf-8") as fh:
            raw = json.load(fh)

        if not isinstance(raw, dict):
            logger.warning(
                "Rate limit file %s has unexpected format — resetting", self._path
            )
            return {}

        result: _RateLimitData = {}
        for key, value in raw.items():
            if isinstance(key, str) and isinstance(value, list):
                result[key] = [float(ts) for ts in value]

        return result

    def _save(self, data: _RateLimitData) -> None:
        """Atomically write rate limit data back to the JSON file."""
        self._path.parent.mkdir(parents=True, exist_ok=True)

        tmp_path = self._path.with_suffix(".tmp")
        with tmp_path.open("w", encoding="utf-8") as fh:
            json.dump(data, fh, separators=(",", ":"))

        os.replace(tmp_path, self._path)
