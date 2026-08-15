"""Tool-level tests: call local_run / local_vision / local_status directly
against a real in-process fake OpenAI server, configured via environment
variables (the quick single-backend channel). Errors are raised as
LocalCallError so the MCP layer marks CallToolResult.isError=true."""

import json
import threading
from http.server import ThreadingHTTPServer

import pytest

from multhands import server
from multhands.config import BASE_URL_ENV, MODEL_ENV
from multhands.errors import LocalCallError

from fakeserver import FakeLocalServer

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


@pytest.fixture()
def fake_server(monkeypatch):
    FakeLocalServer.calls = []
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), FakeLocalServer)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv(BASE_URL_ENV, f"http://127.0.0.1:{httpd.server_address[1]}")
    monkeypatch.setenv(MODEL_ENV, "local-mm")
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()


async def test_local_run_tool(fake_server):
    result = await server.local_run(prompt="say hi")
    assert result["text"] == "hello from fake local"
    assert result["reasoning"] == "I thought about it"
    assert result["model"] == "local-mm"
    assert result["backend"] == "env"
    assert result["usage"]["prompt_tokens"] == 11
    assert isinstance(result["elapsed_ms"], int)


async def test_local_vision_tool(tmp_path, fake_server):
    image = tmp_path / "shot.png"
    image.write_bytes(PNG_BYTES)
    result = await server.local_vision(image_paths=[str(image)], mode="ocr")
    assert result["text"] == "IMAGE SEEN: yes"
    assert result["images"] == 1
    assert result["backend"] == "env"


async def test_local_vision_no_images_raises(fake_server):
    with pytest.raises(LocalCallError) as exc:
        await server.local_vision()
    assert exc.value.code == "INVALID_REQUEST"
    assert "no images" in exc.value.message


async def test_local_vision_bad_mode_raises(fake_server):
    with pytest.raises(LocalCallError) as exc:
        await server.local_vision(mode="bogus", image_paths=["x.png"])
    assert exc.value.code == "INVALID_REQUEST"
    assert "unknown mode" in exc.value.message


async def test_local_vision_compare_needs_multiple(tmp_path, fake_server):
    image = tmp_path / "one.png"
    image.write_bytes(PNG_BYTES)
    with pytest.raises(LocalCallError) as exc:
        await server.local_vision(mode="compare", image_paths=[str(image)])
    assert exc.value.code == "INVALID_REQUEST"
    assert "2-4 images" in exc.value.message


async def test_local_vision_missing_file_raises(tmp_path, fake_server):
    with pytest.raises(LocalCallError) as exc:
        await server.local_vision(image_paths=[str(tmp_path / "nope.png")])
    assert exc.value.code == "INVALID_REQUEST"
    assert "not found" in exc.value.message


async def test_local_status_tool(fake_server):
    result = await server.local_status()
    assert result["backends"][0]["name"] == "env"
    assert result["backends"][0]["reachable"] is True


async def test_local_run_server_not_running(monkeypatch):
    monkeypatch.setenv(BASE_URL_ENV, "http://127.0.0.1:1")
    with pytest.raises(LocalCallError) as exc:
        await server.local_run(prompt="hi")
    assert exc.value.code == "SERVER_NOT_RUNNING"
    assert "start" in exc.value.message


async def test_local_run_no_config(monkeypatch):
    monkeypatch.delenv(BASE_URL_ENV, raising=False)
    monkeypatch.delenv("MULTHANDS_CONFIG", raising=False)
    with pytest.raises(LocalCallError) as exc:
        await server.local_run(prompt="hi")
    assert exc.value.code == "MISCONFIGURED"


async def test_local_run_backend_name_unknown(tmp_path, monkeypatch):
    config = tmp_path / "multhands.json"
    config.write_text(
        '{"backends": {"a": {"baseURL": "http://127.0.0.1:5001"}}}',
        encoding="utf-8",
    )
    monkeypatch.setenv("MULTHANDS_CONFIG", str(config))
    with pytest.raises(LocalCallError) as exc:
        await server.local_run(prompt="hi", backend="ghost")
    assert exc.value.code == "MISCONFIGURED"
    assert "ghost" in exc.value.message


async def test_error_message_carries_code_prefix(monkeypatch):
    monkeypatch.delenv(BASE_URL_ENV, raising=False)
    monkeypatch.delenv("MULTHANDS_CONFIG", raising=False)
    with pytest.raises(LocalCallError) as exc:
        await server.local_run(prompt="hi")
    assert str(exc.value).startswith("[MISCONFIGURED]")


async def test_protocol_level_success_result(fake_server):
    """mcp.call_tool (the MCP layer) must return CallToolResult with text
    content holding the JSON result and no error flag."""
    result = await server.mcp.call_tool("local_run", {"prompt": "say hi"})
    assert result.is_error is False
    assert len(result.content) == 1
    assert result.content[0].type == "text"
    data = json.loads(result.content[0].text)
    assert data["text"] == "hello from fake local"
    assert data["backend"] == "env"
    if result.structured_content is not None:
        assert result.structured_content["result"]["text"] == "hello from fake local"


async def test_protocol_level_error_wrapped_as_tool_error(monkeypatch):
    """Tool failures raise ToolError through the MCP layer; the stdio wire
    handler converts it to CallToolResult(isError=true) (asserted by the
    stdio smoke script)."""
    from mcp.server.mcpserver.exceptions import ToolError

    monkeypatch.delenv(BASE_URL_ENV, raising=False)
    monkeypatch.delenv("MULTHANDS_CONFIG", raising=False)
    with pytest.raises(ToolError) as exc:
        await server.mcp.call_tool("local_run", {"prompt": "hi"})
    assert "[MISCONFIGURED]" in str(exc.value)