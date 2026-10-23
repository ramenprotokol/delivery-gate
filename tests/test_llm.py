from __future__ import annotations

import io
import json
import urllib.error

import pytest

from delivery_gate.llm import (
    DEFAULT_BASE_URL,
    ChatReply,
    LlmClient,
    LlmError,
    _default_transport,
)


def _capture():
    calls = []

    def transport(url, headers, body, timeout):
        calls.append((url, headers, json.loads(body), timeout))
        return {
            "choices": [
                {
                    "message": {
                        "content": "hello",
                        "tool_calls": [
                            {
                                "id": "call_1",
                                "type": "function",
                                "function": {"name": "git_status", "arguments": '{"a": 1}'},
                            }
                        ],
                    }
                }
            ]
        }

    return transport, calls


def test_chat_parses_content_and_tool_calls():
    transport, calls = _capture()
    client = LlmClient(api_key="sk-test-key", model="test-model", transport=transport)
    reply = client.chat([{"role": "user", "content": "hi"}], tools=[{"type": "function"}])

    assert isinstance(reply, ChatReply)
    assert reply.content == "hello"
    assert reply.tool_calls[0].name == "git_status"
    assert reply.tool_calls[0].arguments == {"a": 1}

    url, headers, payload, _ = calls[0]
    assert url == f"{DEFAULT_BASE_URL}/chat/completions"
    assert headers["authorization"] == "Bearer sk-test-key"
    assert payload["model"] == "test-model"
    assert payload["tool_choice"] == "auto"


def test_chat_model_override_reaches_the_payload():
    transport, calls = _capture()
    client = LlmClient(api_key="k", model="flash-model", transport=transport)
    client.chat([{"role": "user", "content": "hi"}], model="big-model")
    assert calls[0][2]["model"] == "big-model"
    client.chat([{"role": "user", "content": "hi"}])
    assert calls[1][2]["model"] == "flash-model"


def test_chat_handles_empty_arguments_and_no_tools():
    def transport(url, headers, body, timeout):
        return {
            "choices": [
                {
                    "message": {
                        "content": "ok",
                        "tool_calls": [
                            {"id": "c", "function": {"name": "git_status", "arguments": ""}}
                        ],
                    }
                }
            ]
        }

    reply = LlmClient(api_key="k", model="test-model", transport=transport).chat(
        [{"role": "user", "content": "x"}]
    )
    assert reply.tool_calls[0].arguments == {}


def test_chat_rejects_malformed_tool_arguments():
    def transport(url, headers, body, timeout):
        return {
            "choices": [
                {
                    "message": {
                        "content": "",
                        "tool_calls": [
                            {"id": "c", "function": {"name": "x", "arguments": "{not json"}}
                        ],
                    }
                }
            ]
        }

    with pytest.raises(LlmError, match="not valid JSON"):
        LlmClient(api_key="k", model="test-model", transport=transport).chat(
            [{"role": "user", "content": "x"}]
        )


def test_chat_rejects_response_without_choices():
    def transport(url, headers, body, timeout):
        return {}

    with pytest.raises(LlmError, match="no choices"):
        LlmClient(api_key="k", model="test-model", transport=transport).chat(
            [{"role": "user", "content": "x"}]
        )


def test_default_transport_reports_http_errors(monkeypatch):
    def boom(request, timeout=None):
        raise urllib.error.HTTPError(request.full_url, 401, "unauthorized", {}, None)

    monkeypatch.setattr("urllib.request.urlopen", boom)
    client = LlmClient(api_key="k", model="test-model")
    with pytest.raises(LlmError, match="HTTP 401"):
        client.chat([{"role": "user", "content": "x"}])


def test_default_transport_retries_503_then_succeeds(monkeypatch):
    attempts = {"n": 0}

    def flaky(request, timeout=None):
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise urllib.error.HTTPError(request.full_url, 503, "unavailable", {}, None)
        return io.BytesIO(b'{"choices": [{"message": {"content": "ok"}}]}')

    monkeypatch.setattr("urllib.request.urlopen", flaky)
    slept: list[float] = []
    data = _default_transport(
        "https://api.example.test/v1/chat/completions", {}, b"{}", 5, sleep=slept.append
    )
    assert attempts["n"] == 3
    assert slept == [1.0, 2.0]
    assert data["choices"][0]["message"]["content"] == "ok"


def test_default_transport_gives_up_after_retrying_503(monkeypatch):
    attempts = {"n": 0}

    def always_503(request, timeout=None):
        attempts["n"] += 1
        raise urllib.error.HTTPError(request.full_url, 503, "unavailable", {}, None)

    monkeypatch.setattr("urllib.request.urlopen", always_503)
    slept: list[float] = []
    with pytest.raises(LlmError, match="HTTP 503"):
        _default_transport(
            "https://api.example.test/v1/chat/completions", {}, b"{}", 5, sleep=slept.append
        )
    assert attempts["n"] == 3
    assert slept == [1.0, 2.0]


def test_default_transport_does_not_retry_other_statuses(monkeypatch):
    attempts = {"n": 0}

    def always_401(request, timeout=None):
        attempts["n"] += 1
        raise urllib.error.HTTPError(request.full_url, 401, "unauthorized", {}, None)

    monkeypatch.setattr("urllib.request.urlopen", always_401)
    slept: list[float] = []
    with pytest.raises(LlmError, match="HTTP 401"):
        _default_transport(
            "https://api.example.test/v1/chat/completions", {}, b"{}", 5, sleep=slept.append
        )
    assert attempts["n"] == 1
    assert slept == []


def _clear_env(monkeypatch):
    for name in (
        "DELIVERY_GATE_LLM_BASE_URL",
        "DELIVERY_GATE_LLM_MODEL",
        "DELIVERY_GATE_LLM_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)


def test_from_env_reads_key_model_and_base_url(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("DELIVERY_GATE_LLM_API_KEY", "sk-test-key")
    monkeypatch.setenv("DELIVERY_GATE_LLM_MODEL", "test-model")
    monkeypatch.setenv("DELIVERY_GATE_LLM_BASE_URL", "https://api.example.test/v1/")
    client = LlmClient.from_env()
    assert client.api_key == "sk-test-key"
    assert client.model == "test-model"
    assert client.base_url == "https://api.example.test/v1"


def test_from_env_defaults_the_base_url_and_prefers_the_model_argument(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("DELIVERY_GATE_LLM_API_KEY", "sk-test-key")
    monkeypatch.setenv("DELIVERY_GATE_LLM_MODEL", "env-model")
    client = LlmClient.from_env(model="arg-model")
    assert client.base_url == DEFAULT_BASE_URL
    assert client.model == "arg-model"


def test_from_env_requires_a_model(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("DELIVERY_GATE_LLM_API_KEY", "sk-test-key")
    with pytest.raises(LlmError, match="DELIVERY_GATE_LLM_MODEL"):
        LlmClient.from_env()


def test_from_env_requires_an_api_key(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("DELIVERY_GATE_LLM_MODEL", "test-model")
    with pytest.raises(LlmError, match="DELIVERY_GATE_LLM_API_KEY"):
        LlmClient.from_env()


def test_the_api_key_never_appears_in_errors_or_reprs(monkeypatch):
    def boom(request, timeout=None):
        raise urllib.error.HTTPError(request.full_url, 401, "unauthorized", {}, None)

    monkeypatch.setattr("urllib.request.urlopen", boom)
    client = LlmClient(api_key="sk-secret-value", model="test-model")
    with pytest.raises(LlmError) as info:
        client.chat([{"role": "user", "content": "x"}])
    assert "sk-secret-value" not in str(info.value)
