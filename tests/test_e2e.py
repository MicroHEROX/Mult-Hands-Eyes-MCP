"""Full-stack behavior tests with the OFFICIAL MCP Python client.

Each test launches the real `python -m multhands` server process and speaks
the complete MCP protocol through the official client implementation (the
same library used by production MCP clients), over both stdio and
Streamable HTTP transports, against a real in-process fake OpenAI backend.

This validates the exact client-visible behavior: handshake/version
negotiation, ping, tools/list schemas, tools/call result parsing
(structured content + isError), and error semantics.
"""

import json
import os
import socket
import subprocess
import sys
import threading
import time
from contextlib import asynccontextmanager
from http.server import ThreadingHTTPServer

import httpx
import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client

from fakeserver import FakeLocalServer

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


def env_for(base_url: str) -> dict:
    env = dict(os.environ)
    env["MULTHANDS_BASE_URL"] = base_url
    env["MULTHANDS_MODEL"] = "local-mm"
    env.pop("MULTHANDS_CONFIG", None)
    env.pop("MULTHANDS_API_KEY", None)
    return env


def wait_http(url: str, timeout: float = 15.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            httpx.post(
                url,
                content=json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 0,
                        "method": "initialize",
                        "params": {
                            "protocolVersion": "2025-03-26",
                            "capabilities": {},
                            "clientInfo": {"name": "ready", "version": "0"},
                        },
                    }
                ),
                headers={
                    "content-type": "application/json",
                    "accept": "application/json, text/event-stream",
                },
                timeout=1,
            )
            return
        except httpx.HTTPError:
            time.sleep(0.1)
    raise RuntimeError(f"server at {url} did not become ready within {timeout}s")


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture()
def fake_backend():
    FakeLocalServer.calls = []
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), FakeLocalServer)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()


@asynccontextmanager
async def mcp_session(base_url: str):
    """Full official-client stdio session against the real server process.

    Entered and exited inside the test task itself (anyio cancel scopes
    must not cross pytest fixture/task boundaries).
    """
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "multhands"],
        env=env_for(base_url),
    )
    with open(os.devnull, "w", encoding="utf-8") as errlog:
        async with stdio_client(params, errlog=errlog) as (read, write):
            async with ClientSession(read, write) as session:
                init = await session.initialize()
                yield session, init


async def test_official_handshake_and_tool_listing(fake_backend):
    async with mcp_session(fake_backend) as (session, init):
        assert init.server_info.name == "multhands"
        assert init.server_info.version

        await session.send_ping()

        tools = await session.list_tools()
        names = [t.name for t in tools.tools]
        assert names == ["local_run", "local_vision", "local_status"]
        for tool in tools.tools:
            assert tool.description, tool.name
            assert tool.input_schema.get("type") == "object"
            assert "properties" in tool.input_schema
        # local_run / local_vision take parameters; local_status is
        # legitimately parameterless.
        assert tools.tools[0].input_schema["properties"]
        assert tools.tools[1].input_schema["properties"]
        assert tools.tools[2].input_schema["properties"] == {}


async def test_official_local_run_roundtrip(fake_backend):
    async with mcp_session(fake_backend) as (session, _init):
        result = await session.call_tool("local_run", {"prompt": "say hi"})
        assert result.is_error is False
        assert len(result.content) == 1
        assert result.content[0].type == "text"
        data = json.loads(result.content[0].text)
        assert data["text"] == "hello from fake local"
        assert data["reasoning"] == "I thought about it"
        assert data["backend"] == "env"
        assert data["usage"]["prompt_tokens"] == 11


async def test_official_local_vision_with_real_image_file(fake_backend, tmp_path):
    async with mcp_session(fake_backend) as (session, _init):
        image = tmp_path / "shot.png"
        image.write_bytes(PNG_BYTES)
        result = await session.call_tool(
            "local_vision", {"mode": "ocr", "image_paths": [str(image)]}
        )
        assert result.is_error is False
        data = json.loads(result.content[0].text)
        assert data["text"] == "IMAGE SEEN: yes"
        assert data["images"] == 1


async def test_official_error_is_protocol_level_iserror(fake_backend):
    """A dead backend must surface as CallToolResult.isError=true."""
    async with mcp_session("http://127.0.0.1:1") as (session, _init):
        result = await session.call_tool("local_run", {"prompt": "hi"})
    assert result.is_error is True
    assert "[SERVER_NOT_RUNNING]" in result.content[0].text


async def test_official_invalid_mode_iserror(fake_backend):
    async with mcp_session(fake_backend) as (session, _init):
        result = await session.call_tool(
            "local_vision", {"mode": "bogus", "image_paths": ["x.png"]}
        )
    assert result.is_error is True
    assert "[INVALID_REQUEST]" in result.content[0].text


async def test_official_local_status(fake_backend):
    async with mcp_session(fake_backend) as (session, _init):
        result = await session.call_tool("local_status", {})
        assert result.is_error is False
        data = json.loads(result.content[0].text)
        backends = data["backends"]
        assert backends[0]["name"] == "env"
        assert backends[0]["reachable"] is True


async def test_official_streamable_http_transport(fake_backend):
    port = free_port()
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "multhands",
            "--transport",
            "streamable-http",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        env=env_for(fake_backend),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        url = f"http://127.0.0.1:{port}/mcp"
        wait_http(url)
        async with streamable_http_client(url) as (read, write):
            async with ClientSession(read, write) as session:
                init = await session.initialize()
                assert init.server_info.name == "multhands"
                tools = await session.list_tools()
                assert [t.name for t in tools.tools] == [
                    "local_run",
                    "local_vision",
                    "local_status",
                ]
                result = await session.call_tool("local_run", {"prompt": "over http"})
                data = json.loads(result.content[0].text)
                assert data["text"] == "hello from fake local"
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=10)


def _unsloth_reachable() -> bool:
    try:
        response = httpx.get("http://127.0.0.1:8888/v1/models", timeout=2)
        return response.status_code in (401, 403, 200)
    except httpx.HTTPError:
        return False


@pytest.mark.skipif(
    not _unsloth_reachable(),
    reason="real Unsloth Desktop not running on 127.0.0.1:8888",
)
async def test_real_unsloth_probe_and_auth_error():
    """Real-world behavior against the user's actual Unsloth instance:
    local_status must report it reachable with an AUTH note, and a real
    call must fail with the actionable [AUTH] hint (no key configured)."""
    async with mcp_session("http://127.0.0.1:8888") as (session, _init):
        status = await session.call_tool("local_status", {})
        data = json.loads(status.content[0].text)
        backend = data["backends"][0]
        assert backend["reachable"] is True
        assert "key" in backend["note"].lower()

        call = await session.call_tool("local_run", {"prompt": "hi"})
        assert call.is_error is True
        assert "[AUTH]" in call.content[0].text
        assert "apiKey" in call.content[0].text