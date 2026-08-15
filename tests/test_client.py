import json

import httpx
import pytest

from multhands.client import (
    ChatCompletion,
    LocalError,
    chat_completion,
    probe,
)
from multhands.config import Backend


def backend(**overrides):
    defaults = dict(
        name="test",
        base_url="http://127.0.0.1:5001",
        model="koboldcpp",
        capabilities=["text", "vision"],
        timeout_ms=10_000,
        max_tokens=8_192,
    )
    defaults.update(overrides)
    return Backend(**defaults)


def response(payload):
    return httpx.Response(200, json=payload, request=httpx.Request("POST", "http://x"))


OK_RESPONSE = {
    "model": "local-model",
    "choices": [{"message": {"content": "hello local"}}],
    "usage": {"prompt_tokens": 12, "completion_tokens": 3},
}


async def test_success():
    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        return response(OK_RESPONSE)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    result = await chat_completion(client, backend(), prompt="say hi")
    assert result.text == "hello local"
    assert result.model == "local-model"
    assert result.prompt_tokens == 12
    assert result.completion_tokens == 3
    assert result.reasoning is None
    assert captured["url"] == "http://127.0.0.1:5001/v1/chat/completions"
    body = captured["body"]
    assert body["messages"] == [{"role": "user", "content": "say hi"}]
    assert body["max_tokens"] == 8_192


async def test_system_and_images_wire():
    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return response(OK_RESPONSE)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    await chat_completion(
        client,
        backend(),
        prompt="read this",
        system="be brief",
        images=["data:image/png;base64,AAAA"],
    )
    body = captured["body"]
    assert body["messages"][0] == {"role": "system", "content": "be brief"}
    user = body["messages"][1]
    assert user["role"] == "user"
    assert user["content"][0] == {"type": "text", "text": "read this"}
    assert user["content"][1] == {
        "type": "image_url",
        "image_url": {"url": "data:image/png;base64,AAAA"},
    }


async def test_reasoning_content_passed_through():
    payload = {
        "model": "m",
        "choices": [{"message": {"content": "answer", "reasoning_content": "thinking..."}}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1},
    }

    async def handler(request: httpx.Request) -> httpx.Response:
        return response(payload)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    result = await chat_completion(client, backend(), prompt="x")
    assert result.reasoning == "thinking..."


async def test_usage_estimated_when_missing():
    payload = {"model": "m", "choices": [{"message": {"content": "A" * 80}}]}

    async def handler(request: httpx.Request) -> httpx.Response:
        return response(payload)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    result = await chat_completion(client, backend(), prompt="x")
    assert result.completion_tokens == 20  # 80 chars / 4


async def test_api_key_header():
    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["auth"] = request.headers.get("authorization")
        return response(OK_RESPONSE)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    await chat_completion(client, backend(api_key="sk-secret"), prompt="x")
    assert captured["auth"] == "Bearer sk-secret"


async def test_no_auth_header_without_key():
    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["auth"] = request.headers.get("authorization")
        return response(OK_RESPONSE)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    await chat_completion(client, backend(), prompt="x")
    assert captured["auth"] is None


async def test_http_401_maps_to_auth():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "unauthorized"}})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    with pytest.raises(LocalError) as exc:
        await chat_completion(client, backend(), prompt="x")
    assert exc.value.code == "AUTH"
    assert "apiKey" in (exc.value.hint or "")


async def test_http_400_context_window():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={"error": {"message": "context window exceeded for this model"}},
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    with pytest.raises(LocalError) as exc:
        await chat_completion(client, backend(), prompt="x" * 1000)
    assert exc.value.code == "CONTEXT_WINDOW_EXCEEDED"


async def test_http_500_maps_to_server():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    with pytest.raises(LocalError) as exc:
        await chat_completion(client, backend(), prompt="x")
    assert exc.value.code == "SERVER"


async def test_connection_error_maps_to_not_running():
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    with pytest.raises(LocalError) as exc:
        await chat_completion(client, backend(), prompt="x")
    assert exc.value.code == "SERVER_NOT_RUNNING"
    assert "start" in (exc.value.hint or "")


async def test_timeout_maps():
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    with pytest.raises(LocalError) as exc:
        await chat_completion(client, backend(timeout_ms=50), prompt="x")
    assert exc.value.code == "TIMEOUT"


async def test_empty_response_maps():
    payload = {"model": "m", "choices": [{"message": {"content": "  "}}]}

    async def handler(request: httpx.Request) -> httpx.Response:
        return response(payload)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    with pytest.raises(LocalError) as exc:
        await chat_completion(client, backend(), prompt="x")
    assert exc.value.code == "EMPTY_RESPONSE"
    assert "mmproj" in (exc.value.hint or "")


async def test_malformed_json_maps():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    with pytest.raises(LocalError) as exc:
        await chat_completion(client, backend(), prompt="x")
    assert exc.value.code == "INVALID_REQUEST"


async def test_probe_ok():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": []})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    reachable, note = await probe(client, backend())
    assert reachable is True
    assert note == "ok"


async def test_probe_auth_counts_reachable():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    reachable, note = await probe(client, backend())
    assert reachable is True
    assert "key" in note


async def test_probe_unreachable():
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    reachable, note = await probe(client, backend())
    assert reachable is False
    assert note == "not reachable"