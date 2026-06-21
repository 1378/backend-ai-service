"""File-based repository for persisting contact request logs."""

import json
import logging
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_LogEntry = dict[str, Any]


class LogRepository:
    """Appends contact request records to a local JSON file.

    Each record is written atomically via a temporary file and :func:`os.replace`
    so that a crash mid-write never corrupts the log.  A :class:`threading.Lock`
    guards the load → append → save cycle to prevent interleaved writes when the
    service handles concurrent requests.
    """

    def __init__(
        self,
        storage_path: Path = Path("data/contact_logs.json"),
    ) -> None:
        self._path = Path(storage_path)
        self._lock = threading.Lock()

    async def save_request(
        self,
        request_data: dict[str, Any],
        sentiment: str,
        auto_reply: str,
    ) -> str:
        """Persist a contact request and return its generated request ID.

        The caller's ``request_data`` dict is not mutated; a copy is stored
        with the email address masked before writing.

        Args:
            request_data: Raw fields from the contact form (name, phone, email, comment).
            sentiment: Sentiment label produced by the AI service.
            auto_reply: Auto-generated reply text produced by the AI service.

        Returns:
            A UUID4 string that uniquely identifies the stored record.
        """
        request_id = str(uuid.uuid4())
        timestamp = datetime.now(timezone.utc).isoformat()

        masked_request_data: dict[str, Any] = {
            **request_data,
            "email": self._mask_email(str(request_data.get("email", ""))),
        }

        entry: _LogEntry = {
            "request_id": request_id,
            "timestamp": timestamp,
            "request_data": masked_request_data,
            "sentiment": sentiment,
            "auto_reply": auto_reply,
        }

        with self._lock:
            logs = self._load_logs()
            logs.append(entry)
            self._save_logs(logs)

        logger.info("Contact request saved with request_id=%s", request_id)
        return request_id

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _load_logs(self) -> list[_LogEntry]:
        """Read all log records from the JSON file.

        Returns an empty list when the file does not exist yet or when its
        contents cannot be parsed as a JSON array.
        """
        if not self._path.exists():
            return []

        try:
            with self._path.open("r", encoding="utf-8") as fh:
                raw = json.load(fh)
        except json.JSONDecodeError:
            logger.warning(
                "Log file %s is corrupted and cannot be parsed — starting fresh",
                self._path,
            )
            return []

        if not isinstance(raw, list):
            logger.warning(
                "Log file %s has unexpected root type %r — starting fresh",
                self._path,
                type(raw).__name__,
            )
            return []

        return raw  # type: ignore[return-value]

    def _save_logs(self, logs: list[_LogEntry]) -> None:
        """Atomically write the full log list back to the JSON file."""
        self._path.parent.mkdir(parents=True, exist_ok=True)

        tmp_path = self._path.with_suffix(".tmp")
        with tmp_path.open("w", encoding="utf-8") as fh:
            json.dump(logs, fh, ensure_ascii=False, indent=2)

        os.replace(tmp_path, self._path)

    @staticmethod
    def _mask_email(email: str) -> str:
        """Return a masked version of the email address.

        The first character of the local part is preserved; the remainder is
        replaced with ``***``.  Examples::

            john.doe@example.com  →  j***@example.com
            a@b.com               →  a***@b.com
        """
        if "@" not in email:
            return "***"

        local, _, domain = email.partition("@")
        masked_local = local[0] + "***" if local else "***"
        return f"{masked_local}@{domain}"
