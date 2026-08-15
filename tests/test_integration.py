"""End-to-end tests against a REAL local HTTP server that speaks the
OpenAI-compatible /v1/chat/completions dialect (as KoboldCpp / llama.cpp
do), including a multimodal request with image parts."""

import threading
from http.server import ThreadingHTTPServer

import httpx
import pytest

from multhands.client import chat_completion
from multhands.config import Backend
from multhands.images import images_to_data_urls

from fakeserver import FakeLocalServer

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


@pytest.fixture(scope="module")
def fake_server():
    FakeLocalServer.calls = []
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), FakeLocalServer)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()


def make_backend(base_url: str) -> Backend:
    return Backend(name="fake", base_url=base_url, model="local-mm", capabilities=["text", "vision"])


async def test_text_roundtrip(fake_server):
    async with httpx.AsyncClient() as client:
        completion = await chat_completion(
            client, make_backend(fake_server), prompt="say hi"
        )
    assert completion.text == "hello from fake local"
    assert completion.reasoning == "I thought about it"
    assert completion.model == "local-mm"
    assert completion.prompt_tokens == 11
    assert completion.completion_tokens == 4


async def test_payload_contains_only_standard_openai_fields(fake_server):
    async with httpx.AsyncClient() as client:
        await chat_completion(
            client,
            make_backend(fake_server),
            prompt="x",
            system="sys",
            temperature=0.5,
            max_tokens=64,
            stop=["</s>"],
        )
    body = FakeLocalServer.calls[-1]
    assert set(body.keys()) == {"model", "messages", "temperature", "max_tokens", "stop"}
    assert body["model"] == "local-mm"
    assert body["temperature"] == 0.5
    assert body["max_tokens"] == 64
    assert body["stop"] == ["</s>"]
    assert body["messages"][0] == {"role": "system", "content": "sys"}
    assert body["messages"][1] == {"role": "user", "content": "x"}


async def test_vision_roundtrip(tmp_path, fake_server):
    image = tmp_path / "shot.png"
    image.write_bytes(PNG_BYTES)
    async with httpx.AsyncClient() as client:
        images = await images_to_data_urls([str(image)], client, 10_000)
        completion = await chat_completion(
            client,
            make_backend(fake_server),
            prompt="analyze this",
            images=images,
        )
    assert completion.text == "IMAGE SEEN: yes"
    last_call = FakeLocalServer.calls[-1]
    user_content = last_call["messages"][-1]["content"]
    assert user_content[0] == {"type": "text", "text": "analyze this"}
    assert user_content[1]["type"] == "image_url"
    assert user_content[1]["image_url"]["url"].startswith("data:image/png;base64,")


async def test_vision_compare_multiple(tmp_path, fake_server):
    a = tmp_path / "a.png"
    b = tmp_path / "b.png"
    a.write_bytes(PNG_BYTES)
    b.write_bytes(PNG_BYTES)
    async with httpx.AsyncClient() as client:
        images = await images_to_data_urls([str(a), str(b)], client, 10_000)
        await chat_completion(
            client, make_backend(fake_server), prompt="compare", images=images
        )
    last_call = FakeLocalServer.calls[-1]
    user_content = last_call["messages"][-1]["content"]
    image_parts = [p for p in user_content if p.get("type") == "image_url"]
    assert len(image_parts) == 2