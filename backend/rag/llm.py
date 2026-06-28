"""
LLM integration for generating responses.
"""
import re
from typing import List, Dict, Any, Optional
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

from core.config import settings


class LLMClient:
    """Client for interacting with Large Language Models."""

    def __init__(self):
        """Initialize LLM client."""
        self.client = None
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

        except Exception as e:
            print(f"Error generating LLM response: {e}")
            return f"Error generating response: {str(e)}"

    def translate_to_georgian(self, text: str) -> str:
        """Translate a query into Georgian for cross-lingual retrieval.

        Uses a dedicated translator prompt (not the tax-assistant system prompt),
        so the corpus, which is in Georgian, is searched with Georgian terms.
        Returns the original text on any failure.
        """
        if not self.client or not (text or "").strip():
            return text
        try:
            messages = [
                SystemMessage(content=(
                    "You are a translator. Translate the user's Georgian tax/legal "
                    "question into Georgian (ქართული). Output ONLY the Georgian "
                    "translation as plain text — no quotes, no explanations, no original text."
                )),
                HumanMessage(content=text),
            ]
            out = self._clean_response_text(self.client.invoke(messages).content)
            return out or text
        except Exception as e:
            print(f"Error translating query: {e}")
            return text

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
        return f"""Вы — AI-ассистент по налоговому законодательству Грузии.
Ваша задача — предоставлять точную информацию на основе официальных документов.

Правила:
1. Отвечайте ТОЛЬКО на основе предоставленного контекста
2. ВСЕГДА указывайте источники информации
3. Если информации недостаточно — четко скажите об этом
4. НЕ придумывайте информацию
5. Используйте язык запроса пользователя для ответа
6. Структурируйте ответ четко и понятно
7. При цитировании законов указывайте статьи и номера документов
8. Не добавляйте markdown-ссылки, raw URL или выдуманные ссылки в текст ответа
9. Источники указывайте только обычным текстом, например: "Источник: <название документа>, статья <номер>"

Контекст из базы данных:
{context}

Предоставьте подробный и точный ответ с указанием источников."""


# Global LLM client instance
llm_client = LLMClient()
