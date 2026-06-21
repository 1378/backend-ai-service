"""AI service for sentiment analysis and auto-reply generation."""

import logging

import openai

from app.config import settings

SENTIMENT_LABELS: frozenset[str] = frozenset({"positive", "neutral", "negative"})
DEFAULT_SENTIMENT = "neutral"
DEFAULT_AUTO_REPLY = (
    "Thank you for reaching out. We have received your message "
    "and will get back to you shortly."
)

_logger = logging.getLogger(__name__)


class AIService:
    """Multi-provider AI service with an OpenAI → Ollama → hardcoded fallback chain.

    Both clients share the OpenAI-compatible async API. All settings are read
    from the application config at construction time.
    """

    def __init__(self) -> None:
        """
        Initialize AIService clients for OpenAI and Ollama using configuration.
        The OpenAI client is only initialized if an API key is provided.
        Ollama client is always enabled.
        """
        self._openai_client = None
        self._ollama_client = None

        self._openai_model = settings.OPENAI_MODEL
        self._ollama_model = settings.OLLAMA_MODEL

        # OpenAI — только если есть ключ
        if settings.OPENAI_API_KEY:
            self._openai_client = openai.AsyncOpenAI(
                api_key=settings.OPENAI_API_KEY,
                base_url=settings.OPENAI_BASE_URL,
            )

        # Ollama всегда включён
        self._ollama_client = openai.AsyncOpenAI(
            api_key="ollama",
            base_url=settings.OLLAMA_BASE_URL,
        )

    # ------------------------------------------------------------------
    # Shared API call helpers
    # ------------------------------------------------------------------

    async def _call_sentiment(
        self,
        client: openai.AsyncOpenAI,
        model: str,
        text: str,
    ) -> str:
        """Execute a sentiment classification request against any OpenAI-compatible client."""
        prompt = (
            "Classify the sentiment of the following text.\n"
            "Respond with exactly one word — positive, neutral, or negative.\n\n"
            f"Text: {text}"
        )
        response = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=10,
            temperature=0,
        )
        label = (response.choices[0].message.content or "").strip().lower()
        return label if label in SENTIMENT_LABELS else DEFAULT_SENTIMENT

    async def _call_reply(
        self,
        client: openai.AsyncOpenAI,
        model: str,
        name: str,
        comment: str,
        sentiment: str,
    ) -> str:
        """Execute a reply-generation request against any OpenAI-compatible client."""
        prompt = self._build_reply_prompt(name, comment, sentiment)
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a multilingual assistant. "
                        "Default language is Russian. "
                        "Follow user language unless overridden."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
       
            max_tokens=150,
            temperature=0.7,
        )
        reply = (response.choices[0].message.content or "").strip()
        return reply if reply else DEFAULT_AUTO_REPLY

    @staticmethod
    def _build_reply_prompt(name: str, comment: str, sentiment: str) -> str:
        return (
            "You are a professional assistant for a website.\n"
            "IMPORTANT: Always respond in Russian language.\n"
            "Do not use English unless the user writes in English.\n\n"
            f"Write a short professional reply to {name} who sent the following message:\n"
            f'"{comment}"\n\n'
            f"The message has a {sentiment} sentiment.\n"
            "Reply in 2-3 sentences. Be warm and concise.\n"
            "Do not include headers or signature."
        )
   

    # ------------------------------------------------------------------
    # Named provider methods — sentiment
    # ------------------------------------------------------------------

    async def _analyze_sentiment_openai(self, text: str) -> str:
        return await self._call_sentiment(self._openai_client, self._openai_model, text)

    async def _analyze_sentiment_ollama(self, text: str) -> str:
        return await self._call_sentiment(self._ollama_client, self._ollama_model, text)

    # ------------------------------------------------------------------
    # Named provider methods — reply generation
    # ------------------------------------------------------------------

    async def _generate_reply_openai(
        self, name: str, comment: str, sentiment: str
    ) -> str:
        return await self._call_reply(
            self._openai_client, self._openai_model, name, comment, sentiment
        )

    async def _generate_reply_ollama(
        self, name: str, comment: str, sentiment: str
    ) -> str:
        return await self._call_reply(
            self._ollama_client, self._ollama_model, name, comment, sentiment
        )

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def analyze_sentiment(self, text: str) -> str:
        """OpenAI → Ollama → fallback"""
        if self._openai_client:
            try:
                _logger.info("OpenAI sentiment analysis started")
                return await self._analyze_sentiment_openai(text)
            except Exception as exc:
                _logger.warning("OpenAI sentiment failed: %s", exc)

        try:
            _logger.info("Ollama sentiment analysis started")
            return await self._analyze_sentiment_ollama(text)
        except Exception as exc:
            _logger.warning("Ollama sentiment failed: %s", exc)

        _logger.warning("Fallback sentiment used")
        return DEFAULT_SENTIMENT
   

    async def generate_auto_reply(
        self,
        name: str,
        comment: str,
        sentiment: str,
    ) -> str:
        """OpenAI → Ollama → fallback"""

        if self._openai_client:
            try:
                _logger.info("OpenAI reply generation started")
                return await self._generate_reply_openai(name, comment, sentiment)
            except Exception as exc:
                _logger.warning("OpenAI reply failed: %s", exc)

        try:
            _logger.info("Ollama reply generation started")
            return await self._generate_reply_ollama(name, comment, sentiment)
        except Exception as exc:
            _logger.warning("Ollama reply failed: %s", exc)

        _logger.warning("Fallback reply used")
        return DEFAULT_AUTO_REPLY
   