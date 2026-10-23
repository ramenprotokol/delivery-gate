from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field

# A plain OpenAI-compatible chat client. Everything is configured through
# environment variables; only the base URL has a default.
DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"

_BASE_URL_ENV = "DELIVERY_GATE_LLM_BASE_URL"
_MODEL_ENV = "DELIVERY_GATE_LLM_MODEL"
_API_KEY_ENV = "DELIVERY_GATE_LLM_API_KEY"

_ERROR_BODY_LIMIT = 300

# The API can briefly answer 503 ("try again shortly"): retry 503s a couple
# of times with a short growing pause, and fail fast on every other status.
_RETRYABLE_STATUS = 503
_MAX_ATTEMPTS = 3
_RETRY_BACKOFF_SECONDS = 1.0


class LlmError(RuntimeError):
    """Raised when the model API cannot be reached, rejects us, or answers oddly."""


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass(frozen=True)
class ChatReply:
    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)


def _default_transport(
    url: str,
    headers: dict[str, str],
    body: bytes,
    timeout: float,
    sleep: Callable[[float], None] = time.sleep,
) -> dict:
    attempt = 0
    while True:
        attempt += 1
        request = urllib.request.Request(url, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as exc:
            if exc.code == _RETRYABLE_STATUS and attempt < _MAX_ATTEMPTS:
                sleep(_RETRY_BACKOFF_SECONDS * attempt)
                continue
            detail = exc.read().decode("utf-8", errors="replace")[:_ERROR_BODY_LIMIT]
            raise LlmError(f"Model API returned HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise LlmError(f"Could not reach the model API: {exc.reason}") from exc
        except ValueError as exc:
            raise LlmError(f"Model API returned a non-JSON response: {exc}") from exc


class LlmClient:
    """A minimal OpenAI-compatible chat client with tool-call support."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str | None = None,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 120.0,
        transport: Callable[[str, dict[str, str], bytes, float], dict] | None = None,
    ):
        self.api_key = api_key
        self.model = model or ""
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._transport = transport or _default_transport

    @classmethod
    def from_env(cls, *, model: str | None = None) -> LlmClient:
        resolved_model = model or os.environ.get(_MODEL_ENV)
        if not resolved_model:
            raise LlmError(
                f"No model set. Set {_MODEL_ENV} (or pass --model) to an open-source "
                "model with tool calling."
            )
        api_key = os.environ.get(_API_KEY_ENV)
        if not api_key or not api_key.strip():
            raise LlmError(f"No API key set. Set {_API_KEY_ENV} to your model API key.")
        return cls(
            api_key=api_key.strip(),
            model=resolved_model,
            base_url=os.environ.get(_BASE_URL_ENV) or DEFAULT_BASE_URL,
        )

    def _headers(self) -> dict[str, str]:
        return {
            "content-type": "application/json",
            "authorization": f"Bearer {self.api_key}",
        }

    def chat(
        self, messages: list[dict], tools: list[dict] | None = None, model: str | None = None
    ) -> ChatReply:
        payload: dict = {"model": model or self.model, "messages": messages}
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        data = self._transport(
            f"{self.base_url}/chat/completions",
            self._headers(),
            json.dumps(payload).encode("utf-8"),
            self.timeout,
        )
        choices = data.get("choices") if isinstance(data, dict) else None
        if not choices:
            raise LlmError("Model API response had no choices.")
        message = choices[0].get("message") or {}
        calls = [
            ToolCall(
                id=str(call.get("id") or ""),
                name=(call.get("function") or {}).get("name") or "",
                arguments=_parse_arguments((call.get("function") or {}).get("arguments")),
            )
            for call in message.get("tool_calls") or []
        ]
        return ChatReply(content=message.get("content") or "", tool_calls=calls)


def _parse_arguments(raw: object) -> dict:
    if raw in (None, ""):
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError) as exc:
        raise LlmError(f"Tool call arguments were not valid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise LlmError("Tool call arguments were not a JSON object.")
    return parsed
