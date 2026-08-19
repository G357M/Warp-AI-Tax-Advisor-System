"""
LLM integration for generating responses.
"""
import hashlib
import logging
import re
from typing import List, Dict, Any, Optional

import redis
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

from core.config import settings


logger = logging.getLogger(__name__)


# Cross-lingual retrieval translates each query once. Two cache layers:
# in-process dict (free repeats within a process) + Redis (persistent across
# processes/restarts — the same query always searches with the same Georgian
# wording, which also makes eval runs reproducible). Redis is fail-open,
# mirroring core/plans.py: translation must never take the chat down.
_TRANSLATION_CACHE: Dict[str, str] = {}
_TRANSLATION_REDIS_PREFIX = "ta:translate:ka:v1:"
_TRANSLATION_REDIS_TTL = 60 * 60 * 24 * 90  # 90 days
_redis_client: Optional[redis.Redis] = None


def _translation_redis() -> Optional[redis.Redis]:
    global _redis_client
    if _redis_client is None:
        try:
            _redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
        except Exception:
            return None
    return _redis_client


def _translation_key(text: str) -> str:
    normalized = re.sub(r"\s+", " ", text.strip().lower())
    return _TRANSLATION_REDIS_PREFIX + hashlib.sha256(normalized.encode("utf-8")).hexdigest()


class LLMClient:
    """Client for interacting with Large Language Models."""

    def __init__(self):
        """Initialize LLM client."""
        self.client = None
        self.translator = None  # dedicated temperature-0 client for query translation
        self._initialize_client()

    def _initialize_client(self):
        """Initialize LLM based on configured provider."""
        try:
            if settings.LLM_PROVIDER == "openai":
                if not settings.OPENAI_API_KEY:
                    print("⚠ Warning: OPENAI_API_KEY not set")
                    return

                self.client = ChatOpenAI(
                    model=settings.LLM_MODEL,
                    temperature=settings.LLM_TEMPERATURE,
                    max_tokens=settings.LLM_MAX_TOKENS,
                    openai_api_key=settings.OPENAI_API_KEY,
                )
                # Translation must be deterministic: at the default generation
                # temperature the Georgian wording drifts between processes and
                # occasionally misses the corpus phrasing (root of the eval
                # noise floor, see docs/RAG_HARDENING_PLAN_2026-07.md П0).
                self.translator = ChatOpenAI(
                    model=settings.LLM_MODEL,
                    temperature=0,
                    max_tokens=settings.LLM_MAX_TOKENS,
                    openai_api_key=settings.OPENAI_API_KEY,
                )
                print(f"✓ OpenAI LLM initialized: {settings.LLM_MODEL}")

            elif settings.LLM_PROVIDER == "anthropic":
                if not settings.ANTHROPIC_API_KEY:
                    print("⚠ Warning: ANTHROPIC_API_KEY not set")
                    return

                self.client = ChatAnthropic(
                    model=settings.LLM_MODEL,
                    temperature=settings.LLM_TEMPERATURE,
                    max_tokens=settings.LLM_MAX_TOKENS,
                    anthropic_api_key=settings.ANTHROPIC_API_KEY,
                )
                self.translator = ChatAnthropic(
                    model=settings.LLM_MODEL,
                    temperature=0,
                    max_tokens=settings.LLM_MAX_TOKENS,
                    anthropic_api_key=settings.ANTHROPIC_API_KEY,
                )
                print(f"✓ Anthropic LLM initialized: {settings.LLM_MODEL}")

        except Exception as e:
            print(f"⚠ Warning: Could not initialize LLM: {e}")
            print(f"⚠ LLM responses will not work until API keys are configured")

    def generate_response(
        self,
        query: str,
        context: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
    ) -> str:
        """
        Generate response using LLM.

        Args:
            query: User query
            context: Retrieved context from documents
            conversation_history: Previous conversation messages

        Returns:
            Generated response text
        """
        if not self.client:
            return "LLM client not initialized. Please check API keys."

        try:
            # Prepare system prompt
            system_prompt = self._build_system_prompt(context)
            print(f"[LLM] Context length: {len(context)} chars")
            print(f"[LLM] Context preview: {context[:200]}..." if len(context) > 200 else f"[LLM] Context: {context}")

            # Prepare messages
            messages = [SystemMessage(content=system_prompt)]

            # Add conversation history if provided
            if conversation_history:
                for msg in conversation_history[-5:]:  # Last 5 messages for context
                    if msg["role"] == "user":
                        messages.append(HumanMessage(content=msg["content"]))
                    # Note: SystemMessage for assistant responses in LangChain

            # Add current query
            messages.append(HumanMessage(content=query))

            # Generate response
            response = self.client.invoke(messages)
            return self._clean_response_text(response.content)

        except Exception:
            logger.exception("LLM response generation failed")
            return "Извините, сейчас не удалось сформировать ответ. Попробуйте ещё раз позднее."

    def translate_to_georgian(self, text: str) -> str:
        """Translate a query into Georgian for cross-lingual retrieval.

        Uses a dedicated translator prompt (not the tax-assistant system prompt),
        so the corpus, which is in Georgian, is searched with Georgian terms.
        Returns the original text on any failure.
        """
        key = (text or "").strip()
        if not self.client or not key:
            return text
        if key in _TRANSLATION_CACHE:
            return _TRANSLATION_CACHE[key]
        redis_key = _translation_key(key)
        client = _translation_redis()
        if client is not None:
            try:
                cached = client.get(redis_key)
                if cached:
                    if len(_TRANSLATION_CACHE) < 5000:
                        _TRANSLATION_CACHE[key] = cached
                    return cached
            except Exception:
                pass
        try:
            messages = [
                SystemMessage(content=(
                    "You are a translator for searching a Georgian tax-law corpus. "
                    "Translate the user's tax/legal question into Georgian (ქართული) "
                    "using standard Georgian legal/tax terminology — never Latin "
                    "abbreviations or transliterations. For example: VAT/НДС → დღგ, "
                    "income tax → საშემოსავლო გადასახადი, profit tax → მოგების გადასახადი, "
                    "property tax → ქონების გადასახადი, pension contribution → საპენსიო შენატანი, "
                    "micro business → მიკრო ბიზნესი (always two words, never merged as "
                    "'მიკრობიზნესი' — the Tax Code spells it with a space), small business → "
                    "მცირე ბიზნესი. Keep numbers as digits. Output ONLY the Georgian translation as plain "
                    "text — no quotes, no explanations, no Latin letters, no original text."
                )),
                HumanMessage(content=text),
            ]
            translator = self.translator or self.client
            out = self._clean_response_text(translator.invoke(messages).content) or text
        except Exception as e:
            print(f"Error translating query: {e}")
            # Do not cache failures — the next call should retry the LLM.
            return text
        if len(_TRANSLATION_CACHE) < 5000:
            _TRANSLATION_CACHE[key] = out
        if client is not None and out != text:
            try:
                client.set(redis_key, out, ex=_TRANSLATION_REDIS_TTL)
            except Exception:
                pass
        return out

    def _clean_response_text(self, text: Any) -> str:
        cleaned = str(text or "")
        cleaned = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r"\1", cleaned)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        return cleaned.strip()

    def _build_system_prompt(self, context: str) -> str:
        """
        Build system prompt with context.

        Args:
            context: Retrieved context from documents

        Returns:
            System prompt text
        """
        return f"""Вы — ассистент по налоговому законодательству Грузии. Отвечаете СТРОГО по приведённому ниже контексту из официальных документов.

ЖЁСТКИЕ ПРАВИЛА:
1. Используйте ТОЛЬКО факты, прямо присутствующие в контексте. НИКОГДА не добавляйте сведения из общих знаний или памяти, даже если уверены в них.
2. Если в контексте нет прямого ответа на заданный вопрос — ответьте ровно одной фразой: "В предоставленных официальных источниках ответ на этот вопрос не найден." Ничего не додумывайте и не предлагайте догадок.
3. Не называйте ставки, суммы, сроки, проценты или номера статей, которых нет в контексте.
4. Если ответ есть — дайте его кратко и по делу, затем укажите статью/документ из контекста в формате: "Источник: <название документа>, статья <номер>".
5. Отвечайте на языке вопроса пользователя.
6. Без markdown-разметки, без ссылок-URL и выдуманных ссылок в тексте.

Контекст из базы законов:
{context}

Ответ строго по контексту:"""


# Global LLM client instance
llm_client = LLMClient()
