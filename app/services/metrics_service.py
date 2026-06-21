"""File-based service for tracking contact submission metrics."""

import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_logger = logging.getLogger(__name__)

_VALID_SENTIMENTS: frozenset[str] = frozenset({"positive", "neutral", "negative"})

_Metrics = dict[str, Any]


class MetricsService:
    """Persists and retrieves contact submission statistics in a local JSON file.

    Writes are atomic (temp file + :func:`os.replace`) and protected by a
    :class:`threading.Lock` so concurrent requests never corrupt the metrics file.
    """

    def __init__(
        self,
        storage_path: Path = Path("data/metrics.json"),
    ) -> None:
        self._path = Path(storage_path)
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def record_submission(self, sentiment: str) -> None:
        """Increment submission counters and update the last-updated timestamp.

        Args:
            sentiment: Sentiment label for the submission. Must be one of
                       ``positive``, ``neutral``, or ``negative``.  Unknown
                       labels are accepted but only the total counter is
                       incremented.
        """
        with self._lock:
            metrics = self._load_metrics()
            metrics["total_submissions"] += 1

            if sentiment in _VALID_SENTIMENTS:
                metrics[sentiment] += 1
            else:
                _logger.warning(
                    "Unknown sentiment label %r — total_submissions incremented only",
                    sentiment,
                )

            metrics["last_updated"] = datetime.now(timezone.utc).isoformat()
            self._save_metrics(metrics)

        _logger.info(
            "Metrics updated: total=%d sentiment=%r",
            metrics["total_submissions"],
            sentiment,
        )

    async def get_metrics(self) -> _Metrics:
        """Return the current metrics snapshot.

        Returns the default metrics structure when the file does not exist yet.
        """
        with self._lock:
            return self._load_metrics()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _load_metrics(self) -> _Metrics:
        """Read metrics from the JSON file.

        Returns the default structure when the file is missing or corrupted.
        """
        if not self._path.exists():
            return self._default_metrics()

        try:
            with self._path.open("r", encoding="utf-8") as fh:
                raw = json.load(fh)
        except (json.JSONDecodeError, OSError):
            _logger.warning(
                "Metrics file %s is corrupted or unreadable — using default metrics",
                self._path,
            )
            return self._default_metrics()

        if not isinstance(raw, dict):
            _logger.warning(
                "Metrics file %s has unexpected root type %r — using default metrics",
                self._path,
                type(raw).__name__,
            )
            return self._default_metrics()

        return raw  # type: ignore[return-value]

    def _save_metrics(self, metrics: _Metrics) -> None:
        """Atomically write the metrics dict to the JSON file."""
        self._path.parent.mkdir(parents=True, exist_ok=True)

        tmp_path = self._path.with_suffix(".tmp")
        with tmp_path.open("w", encoding="utf-8") as fh:
            json.dump(metrics, fh, ensure_ascii=False, indent=2)

        os.replace(tmp_path, self._path)

    @staticmethod
    def _default_metrics() -> _Metrics:
        """Return a zeroed-out metrics structure."""
        return {
            "total_submissions": 0,
            "positive": 0,
            "neutral": 0,
            "negative": 0,
            "last_updated": None,
        }
