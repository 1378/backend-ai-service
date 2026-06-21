"""Email notification service using SMTP with a logging-only fallback."""

import asyncio
import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)

class SMTPConfig:
    def __init__(self):
        self.host = os.getenv("SMTP_HOST")
        self.port = int(os.getenv("SMTP_PORT", "587"))
        self.user = os.getenv("SMTP_USER")
        self.password = os.getenv("SMTP_PASS")
        self.from_email = os.getenv("SMTP_FROM", self.user)

    def is_valid(self) -> bool:
        return bool(self.host and self.user and self.password)

def _build_smtp_config() -> Optional[dict]:
    """Return SMTP config dict from environment, or None when SMTP_HOST is absent."""
    host = os.getenv("SMTP_HOST")
    if not host:
        return None

    port_raw = os.getenv("SMTP_PORT", "587")
    try:
        port = int(port_raw)
    except ValueError:
        logger.warning("Invalid SMTP_PORT value %r, defaulting to 587", port_raw)
        port = 587

    return {
        "host": host,
        "port": port,
        "user": os.getenv("SMTP_USER"),
        "password": os.getenv("SMTP_PASS"),
    }


def _send_via_smtp(subject: str, body: str, recipient: str) -> None:
    """Perform a blocking SMTP delivery. Raises on any failure."""
    config = _build_smtp_config()
    if config is None:
        raise RuntimeError("SMTP is not configured")

    sender: str = config["user"] or "noreply@localhost"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = recipient
    msg.attach(MIMEText(body, "plain", "utf-8"))

    with smtplib.SMTP(self._smtp.host, self._smtp.port) as server:
        server.ehlo()
        server.starttls()
        if self._smtp.user and self._smtp.password:
            server.login(self._smtp.user, self._smtp.password)
        server.sendmail(
            self._smtp.from_email,
            recipient,
            msg.as_string()
        )
   


def _log_email(subject: str, body: str, recipient: str) -> None:
    """Write the full email payload to the application log."""
    logger.info(
        "EMAIL (log-only mode)\nTo: %s\nSubject: %s\n\n%s",
        recipient,
        subject,
        body,
    )


class EmailService:
    """Sends transactional emails via SMTP with a log-only fallback.

    When SMTP_HOST is not set, emails are written to the application log
    instead of being delivered. This keeps the service fully usable in
    local development with zero external dependencies.

    All delivery failures are caught internally and never propagated to
    the caller, so the main request flow is never interrupted.
    """

    def __init__(self) -> None:
        self._smtp = SMTPConfig()
        self._smtp_enabled = self._smtp.is_valid()
   
        if not self._smtp_enabled:
            logger.info("EmailService: SMTP not configured — running in log-only mode")

    async def send_owner_notification(
        self,
        name: str,
        phone: str,
        email: str,
        comment: str,
        sentiment: str,
        auto_reply: str,
    ) -> None:
        """Notify the site owner about a new contact submission."""
        owner_email = settings.OWNER_EMAIL
        if not owner_email:
            logger.warning(
                "OWNER_EMAIL not set — skipping owner notification (contact from %s)",
                email,
            )
            return

        subject = f"New contact request from {name}"
        body = (
            f"New contact form submission\n"
            f"{'=' * 40}\n"
            f"Name:      {name}\n"
            f"Phone:     {phone}\n"
            f"Email:     {email}\n"
            f"Sentiment: {sentiment}\n"
            f"\nComment:\n{comment}\n"
            f"\nAuto-reply sent to user:\n{auto_reply}\n"
        )

        await self._dispatch(subject, body, owner_email)

    async def send_user_confirmation(
        self,
        email: str,
        name: str,
        auto_reply: str,
    ) -> None:
        """Send a confirmation email to the submitting user."""
        subject = "We received your message"
        body = (
            f"Hi {name},\n\n"
            f"{auto_reply}\n\n"
            f"Best regards,\n"
            f"{settings.APP_NAME}\n"
        )

        await self._dispatch(subject, body, email)

    async def _dispatch(self, subject: str, body: str, recipient: str) -> None:
        """Deliver via SMTP, or fall back to log-only on any failure."""
        if not self._smtp_enabled:
            _log_email(subject, body, recipient)
            return

        try:
            await asyncio.to_thread(_send_via_smtp, subject, body, recipient)
            logger.info("Email sent | To: %s | Subject: %s", recipient, subject)
        except Exception as exc:
            logger.error(
                "SMTP delivery failed, falling back to log-only | To: %s | Error: %s",
                recipient,
                exc,
            )
            _log_email(subject, body, recipient)
