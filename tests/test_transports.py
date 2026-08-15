"""Transport compatibility tests: legacy MCP protocol versions over stdio
(Claude Desktop 2024-11-05, Cline/Cursor/opencode 2025-03-26, newest
2025-06-18) and the streamable HTTP transport for network/browser clients.
"""

import json
import subprocess
import sys

import httpx
import pytest
from asgi_lifespan import LifespanManager

from multhands.server import mcp, parse_args


def _stdio_rpc(proc, method, params=None, msg_id=0):
    payload = {"jsonrpc": "2.0", "id": msg_id, "method": method}
    if params is not None:
        payload["params"] = params
    proc.stdin.write(json.dumps(payload) + "\n")
    proc.stdin.flush()
    while True:
        line = proc.stdout.readline()
        if not line:
            raise RuntimeError("stdout closed")
        obj = json.loads(line)
        if obj.get("id") == msg_id:
            return obj


@pytest.mark.parametrize("version", ["2024-11-05", "2025-03-26", "2025-06-18"])
def test_stdio_negotiates_legacy_protocol_versions(version):
    """Old clients must still be able to initialize over stdio."""
    proc = subprocess.Popen(
        [sys.executable, "-m", "multhands"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        bufsize=1,
    )
    try:
        init = _stdio_rpc(
            proc,
            "initialize",
            {
                "protocolVersion": version,
                "capabilities": {},
                "clientInfo": {"name": "compat-probe", "version": "0"},
            },
            1,
        )
        assert init["result"]["protocolVersion"] == version
        assert init["result"]["serverInfo"]["name"] == "multhands"
        _stdio_rpc(proc, "notifications/initialized", {}, 2)
        tools = _stdio_rpc(proc, "tools/list", {}, 3)
        assert [t["name"] for t in tools["result"]["tools"]] == [
            "local_run",
            "local_vision",
            "local_status",
        ]
    finally:
        proc.stdin.close()
        proc.wait(timeout=10)


async def test_streamable_http_end_to_end(monkeypatch):
    """A raw HTTP client can initialize, list tools, and call tools over
    POST /mcp — the transport used by remote/browser-based MCP platforms."""
    monkeypatch.delenv("MULTHANDS_BASE_URL", raising=False)
    monkeypatch.delenv("MULTHANDS_CONFIG", raising=False)
    app = mcp.streamable_http_app()
    headers = {
        # MCP spec: clients MUST accept both JSON and event-stream.
        "content-type": "application/json",
        "accept": "application/json, text/event-stream",
    }

    def extract(response: httpx.Response) -> dict:
        """Pull the JSON-RPC message out of a JSON or SSE response body."""
        if response.headers.get("content-type", "").startswith("text/event-stream"):
            for line in response.text.splitlines():
                if line.startswith("data:"):
                    return json.loads(line[len("data:"):].strip())
        return response.json()

    async with LifespanManager(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8000"
        ) as client:
            init = await client.post(
                "/mcp",
                content=json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "initialize",
                        "params": {
                            "protocolVersion": "2025-03-26",
                            "capabilities": {},
                            "clientInfo": {"name": "http-probe", "version": "0"},
                        },
                    }
                ),
                headers=headers,
            )
            assert init.status_code == 200
            assert extract(init)["result"]["serverInfo"]["name"] == "multhands"
            # 2025-03-26 streamable HTTP spec: the server assigns a session id
            # at initialize; the client MUST echo it on later requests.
            session_id = init.headers.get("mcp-session-id")
            assert session_id
            headers["mcp-session-id"] = session_id

            tools = await client.post(
                "/mcp",
                content=json.dumps(
                    {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
                ),
                headers=headers,
            )
            names = [t["name"] for t in extract(tools)["result"]["tools"]]
            assert names == ["local_run", "local_vision", "local_status"]

            call = await client.post(
                "/mcp",
                content=json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 3,
                        "method": "tools/call",
                        "params": {"name": "local_run", "arguments": {"prompt": "hi"}},
                    }
                ),
                headers=headers,
            )
            result = extract(call)["result"]
            assert result["isError"] is True
            assert "[MISCONFIGURED]" in result["content"][0]["text"]


def test_cli_defaults_to_stdio():
    args = parse_args([])
    assert args.transport == "stdio"


def test_cli_http_options():
    args = parse_args(["--transport", "streamable-http", "--host", "0.0.0.0", "--port", "8020"])
    assert args.transport == "streamable-http"
    assert args.host == "0.0.0.0"
    assert args.port == 8020
    args = parse_args(["--transport", "sse"])
    assert args.transport == "sse"