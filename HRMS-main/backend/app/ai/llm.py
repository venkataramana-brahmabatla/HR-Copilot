import asyncio
import json
import socket
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.core.config import settings


class LLMError(Exception):
    """Base error for model configuration and provider failures."""


class LLMConfigurationError(LLMError):
    pass


class LLMTimeoutError(LLMError):
    pass


class LLMProviderError(LLMError):
    pass


class LLMClient:
    """Small async wrapper for OpenAI-compatible chat completion APIs."""

    async def generate(self, messages: list[dict[str, str]]) -> str:
        if not settings.groq_api_key:
            raise LLMConfigurationError("GROQ_API_KEY is not configured")

        response_data = await self._complete({"messages": messages})
        try:
            answer = response_data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMProviderError("Model provider returned an invalid response") from exc

        if not isinstance(answer, str) or not answer.strip():
            raise LLMProviderError("Model provider returned an empty response")
        return answer.strip()

    async def _complete(self, completion: dict) -> dict:
        if not settings.groq_api_key:
            raise LLMConfigurationError("GROQ_API_KEY is not configured")

        payload = json.dumps(
            {
                "model": settings.llm_model,
                "include_reasoning": False,
                **completion,
            }
        ).encode("utf-8")
        request = Request(
            url=f"{settings.llm_base_url.rstrip('/')}/chat/completions",
            data=payload,
            headers={
                "Authorization": f"Bearer {settings.groq_api_key}",
                "Content-Type": "application/json",
                # Groq's edge rejects Python's default Python-urllib user agent.
                "User-Agent": "HR-Copilot/0.1",
            },
            method="POST",
        )

        try:
            response_body = await asyncio.to_thread(self._send, request)
        except HTTPError as exc:
            raise LLMProviderError(f"Model provider returned HTTP {exc.code}") from exc
        except (TimeoutError, socket.timeout) as exc:
            raise LLMTimeoutError("Model provider request timed out") from exc
        except URLError as exc:
            if isinstance(exc.reason, (TimeoutError, socket.timeout)):
                raise LLMTimeoutError("Model provider request timed out") from exc
            raise LLMProviderError("Could not connect to the model provider") from exc

        try:
            response_data = json.loads(response_body)
        except json.JSONDecodeError as exc:
            raise LLMProviderError("Model provider returned an invalid response") from exc
        if not isinstance(response_data, dict):
            raise LLMProviderError("Model provider returned an invalid response")
        return response_data

    @staticmethod
    def _send(request: Request) -> bytes:
        with urlopen(request, timeout=settings.llm_timeout_seconds) as response:
            return response.read()


llm_client = LLMClient()
