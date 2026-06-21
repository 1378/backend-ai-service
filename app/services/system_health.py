import logging
import httpx
import smtplib

from app.config import settings
from app.services.ai_service import AIService

logger = logging.getLogger(__name__)


class SystemHealthService:
    """Checks external dependencies on startup."""

    def __init__(self) -> None:
        self.ai = AIService()

    async def check_openai(self) -> bool:
        if not settings.OPENAI_API_KEY:
            return False

        try:
            await self.ai.analyze_sentiment("test")
            return True
        except Exception as exc:
            logger.warning("OpenAI health check failed: %s", exc)
            return False

    async def check_ollama(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=3) as client:
                r = await client.get(f"{settings.OLLAMA_BASE_URL}/models")
                return r.status_code == 200
        except Exception as exc:
            logger.warning("Ollama health check failed: %s", exc)
            return False

    def check_smtp(self) -> bool:
        try:
            if not settings.OWNER_EMAIL:
                return False

            host = settings.OWNER_EMAIL and settings.OWNER_EMAIL.split("@")[-1]

            # просто проверка конфига (без реальной отправки)
            required = [
                "SMTP_HOST",
                "SMTP_PORT",
                "SMTP_USER",
                "SMTP_PASS",
            ]

            return all(getattr(settings, k, None) or __import__("os").getenv(k) for k in required)
        except Exception as exc:
            logger.warning("SMTP health check failed: %s", exc)
            return False

    def print_report(self, openai_ok: bool, ollama_ok: bool, smtp_ok: bool) -> None:
        logger.info("\n================ SYSTEM HEALTH ================")
        logger.info("OpenAI : %s", "OK" if openai_ok else "FAIL")
        logger.info("Ollama : %s", "OK" if ollama_ok else "FAIL")
        logger.info("SMTP   : %s", "OK" if smtp_ok else "NOT CONFIGURED")
        logger.info("===============================================")