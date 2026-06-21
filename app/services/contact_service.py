"""Contact form business logic."""

import re
import uuid
from typing import Any, Protocol

from pydantic import BaseModel

from app.models.contact import ContactRequest

DEFAULT_SENTIMENT = "neutral"
DEFAULT_AUTO_REPLY = (
    "Thank you for reaching out. We have received your message "
    "and will get back to you shortly."
)
SUCCESS_MESSAGE = "Your contact request has been submitted successfully."

WHITESPACE_PATTERN = re.compile(r"\s+")


class ContactServiceResponse(BaseModel):
    """Structured result of a processed contact submission."""

    request_id: str
    message: str
    sentiment: str
    auto_reply: str
    emails_sent: bool


class RateLimitExceededError(Exception):
    """Raised when a client exceeds the configured request rate."""


class AIServiceProtocol(Protocol):
    """Expected interface for app.services.ai_service.AIService."""

    async def analyze_sentiment(self, text: str) -> str:
        """Return sentiment label for the given text."""

    async def generate_auto_reply(
        self,
        name: str,
        comment: str,
        sentiment: str,
    ) -> str:
        """Return an auto-generated reply for the contact submission."""


class EmailServiceProtocol(Protocol):
    """Expected interface for app.services.email_service.EmailService."""

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

    async def send_user_confirmation(
        self,
        email: str,
        name: str,
        auto_reply: str,
    ) -> None:
        """Send a confirmation email to the submitting user."""


class LogRepositoryProtocol(Protocol):
    """Expected interface for app.repositories.log_repository.LogRepository."""

    async def save_request(
        self,
        request_data: dict[str, Any],
        sentiment: str,
        auto_reply: str,
    ) -> str:
        """Persist the contact request and return its identifier."""


class MetricsServiceProtocol(Protocol):
    """Expected interface for app.services.metrics_service.MetricsService."""

    async def record_submission(self, sentiment: str) -> None:
        """Update submission metrics for the given sentiment."""


class RateLimitServiceProtocol(Protocol):
    """Expected interface for rate-limit enforcement."""

    async def check_rate_limit(self, client_key: str) -> None:
        """Raise RateLimitExceededError when the client key is over limit."""


class LoggerProtocol(Protocol):
    """Expected interface for app.middleware.logger application logger."""

    def info(self, message: str, **kwargs: Any) -> None:
        """Log an informational message."""

    def warning(self, message: str, **kwargs: Any) -> None:
        """Log a warning message."""

    def error(self, message: str, **kwargs: Any) -> None:
        """Log an error message."""


def _normalize_text(value: str) -> str:
    """Collapse repeated whitespace and trim surrounding space."""
    return WHITESPACE_PATTERN.sub(" ", value.strip())


def _normalize_phone(value: str) -> str:
    """Normalize phone formatting while preserving allowed characters."""
    return WHITESPACE_PATTERN.sub(" ", value.strip())


def _sanitize_request(request: ContactRequest) -> ContactRequest:
    """Apply basic normalization to validated contact input."""
    return ContactRequest(
        name=_normalize_text(request.name),
        phone=_normalize_phone(request.phone),
        email=str(request.email).strip().lower(),
        comment=_normalize_text(request.comment),
    )


def _request_to_dict(request: ContactRequest) -> dict[str, Any]:
    """Convert a contact request into a log-friendly dictionary."""
    return {
        "name": request.name,
        "phone": request.phone,
        "email": str(request.email),
        "comment": request.comment,
    }


class ContactService:
    """Orchestrates contact form submission processing."""

    def __init__(
        self,
        ai_service: AIServiceProtocol,
        email_service: EmailServiceProtocol,
        log_repository: LogRepositoryProtocol,
        metrics_service: MetricsServiceProtocol,
        rate_limit_service: RateLimitServiceProtocol,
        logger: LoggerProtocol,
    ) -> None:
        self._ai_service = ai_service
        self._email_service = email_service
        self._log_repository = log_repository
        self._metrics_service = metrics_service
        self._rate_limit_service = rate_limit_service
        self._logger = logger

    async def process_contact(
        self,
        request: ContactRequest,
        client_key: str,
    ) -> ContactServiceResponse:
        """Process a contact submission end-to-end."""
        await self._enforce_rate_limit(client_key)

        sanitized_request = _sanitize_request(request)
        sentiment, auto_reply = await self._resolve_ai_insights(sanitized_request)
        request_id = await self._persist_request_log(
            sanitized_request,
            sentiment,
            auto_reply,
        )
        await self._update_metrics(sentiment)
        emails_sent = await self._dispatch_emails(
            sanitized_request,
            sentiment,
            auto_reply,
        )

        self._logger.info(
            "Contact request processed",
            request_id=request_id,
            sentiment=sentiment,
            emails_sent=emails_sent,
        )

        return ContactServiceResponse(
            request_id=request_id,
            message=SUCCESS_MESSAGE,
            sentiment=sentiment,
            auto_reply=auto_reply,
            emails_sent=emails_sent,
        )

    async def _enforce_rate_limit(self, client_key: str) -> None:
        """Apply rate limiting for the submitting client."""
        try:
            await self._rate_limit_service.check_rate_limit(client_key)
        except RateLimitExceededError:
            raise
        except Exception as exc:
            self._logger.error(
                "Rate limit check failed",
                client_key=client_key,
                error=str(exc),
            )
            raise

    async def _resolve_ai_insights(
        self,
        request: ContactRequest,
    ) -> tuple[str, str]:
        """Run AI analysis with graceful fallback when the provider fails."""
        sentiment = DEFAULT_SENTIMENT
        auto_reply = DEFAULT_AUTO_REPLY

        try:
            sentiment = await self._ai_service.analyze_sentiment(request.comment)
        except Exception as exc:
            self._logger.warning(
                "Sentiment analysis failed, using fallback",
                error=str(exc),
            )

        try:
            auto_reply = await self._ai_service.generate_auto_reply(
                name=request.name,
                comment=request.comment,
                sentiment=sentiment,
            )
        except Exception as exc:
            self._logger.warning(
                "Auto reply generation failed, using fallback",
                error=str(exc),
            )

        return sentiment, auto_reply

    async def _persist_request_log(
        self,
        request: ContactRequest,
        sentiment: str,
        auto_reply: str,
    ) -> str:
        """Save the request log and return a stable identifier."""
        request_id = str(uuid.uuid4())

        try:
            request_id = await self._log_repository.save_request(
                request_data=_request_to_dict(request),
                sentiment=sentiment,
                auto_reply=auto_reply,
            )
        except Exception as exc:
            self._logger.error(
                "Failed to save contact request log",
                request_id=request_id,
                error=str(exc),
            )

        return request_id

    async def _update_metrics(self, sentiment: str) -> None:
        """Record submission metrics without interrupting the main flow."""
        try:
            await self._metrics_service.record_submission(sentiment)
        except Exception as exc:
            self._logger.error(
                "Failed to update contact metrics",
                sentiment=sentiment,
                error=str(exc),
            )

    async def _dispatch_emails(
        self,
        request: ContactRequest,
        sentiment: str,
        auto_reply: str,
    ) -> bool:
        """Send owner and user emails; failures are logged, not propagated."""
        emails_sent = True

        try:
            await self._email_service.send_owner_notification(
                name=request.name,
                phone=request.phone,
                email=str(request.email),
                comment=request.comment,
                sentiment=sentiment,
                auto_reply=auto_reply,
            )
        except Exception as exc:
            emails_sent = False
            self._logger.error(
                "Failed to send owner notification email",
                email=str(request.email),
                error=str(exc),
            )

        try:
            await self._email_service.send_user_confirmation(
                email=str(request.email),
                name=request.name,
                auto_reply=auto_reply,
            )
        except Exception as exc:
            emails_sent = False
            self._logger.error(
                "Failed to send user confirmation email",
                email=str(request.email),
                error=str(exc),
            )

        return emails_sent
