<div align="center">

# Mult Hands Eyes MCP

**Give your online LLM a pair of local hands — and local eyes.**

[![version](https://img.shields.io/badge/version-0.1.0-blue)](https://github.com/MicroHEROX/Mult-Hands-Eyes-MCP/releases)
[![license](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![python](https://img.shields.io/badge/python-%E2%89%A53.10-3776AB?logo=python)](https://python.org)
[![mcp](https://img.shields.io/badge/MCP-stdio%20%7C%20SSE%20%7C%20Streamable%20HTTP-8A2BE2)](https://modelcontextprotocol.io)
[![tests](https://img.shields.io/badge/tests-81%20passed-brightgreen)](docs/engineering.md)

**Language** &nbsp;|&nbsp; [**English**](README.md) &nbsp;•&nbsp; [**简体中文**](README.zh-CN.md)

</div>

A **platform-agnostic [MCP](https://modelcontextprotocol.io) server** that lets your **online LLM** (opencode, Claude Desktop, Cursor, Cline, Windsurf, Cherry Studio, …) hand off repetitive, token-wasting grunt work to **OpenAI-compatible local inference services** running on this machine — **text work** *and* **vision work** (image understanding / OCR / image comparison).

The main model stays exactly where your deployment puts it. When a task is cheaper to do locally, the model calls:

- **`local_run`** — run one prompt on a local **text** model: batch rewrites, name translations, string munging, deduplication, short summaries, structured extraction.
- **`local_vision`** — send images to a local **multimodal** model: OCR, image analysis, multi-image comparison, using structured report templates. Text-only online models get their eyes this way: pass an image path or URL, get text back.
- **`local_status`** — list configured backends and probe their health.

The server is a **pure client**: it never starts, owns, or kills any process, and never writes any file. It only talks HTTP to the services **you** run.

---

## What it does

- **Two model-facing tools** (`local_run`, `local_vision`) plus a diagnostics tool (`local_status`), registered with the official MCP Python SDK (≥ 2.0).
- **Any OpenAI-compatible endpoint**: KoboldCpp, Unsloth Desktop, llama.cpp server, LM Studio, Ollama `/v1`, text-generation-webui — declared per backend in one JSON config, with `text` / `vision` capability routing.
- **Structured vision reports**: `analyze` (8-section report), `ocr` (character-exact extraction), `compare` (2–4 images, joint reasoning, 5-section report), plus a fidelity rule (relay verbatim, never invent, preserve uncertainty).
- **Three image sources** for vision: local file paths, `data:` URLs, `http(s)://` URLs (downloaded server-side and re-encoded — the local model never needs internet).
- **Three transports**: stdio (default, zero-arg launch), SSE, and Streamable HTTP — protocol versions 2024-11-05 / 2025-03-26 / 2025-06-18 / 2025-11-25 verified against the official MCP client.
- **Hot-reloaded config**: the JSON file is re-read on every call; edit it without restarting. A temporarily broken file falls back to the last good one.
- **Spec-compliant errors**: every failure surfaces as protocol-level `CallToolResult.isError=true` with a stable `[CODE]` and an actionable hint the model can self-heal from.
- **Installable two ways**: `uv tool install .` (Python) or `npx mult-hands-eyes-mcp` (npm wrapper that bootstraps its own Python venv).

## What it does NOT do

- **Does not replace** your model provider — the online model is always the brain; local models are reachable only through the two tools.
- **Does not start, configure, or stop** any local service, and never scans ports or auto-detects servers. Endpoints are explicitly configured by you.
- **Does not bundle or host** model files (GGUF / mmproj). Bring your own.
- **Does not stream** — one tool call, one complete answer (simpler and sufficient).
- **Does not modify** any client config file — you add the MCP entry yourself.

---

## Requirements

| Item | Requirement |
| --- | --- |
| Python | ≥ 3.10 (the npm wrapper checks this for you) |
| A local service | any OpenAI-compatible server, e.g. KoboldCpp (port 5001), Unsloth Desktop (8888), llama-server (8080), LM Studio (1234), Ollama (11434) |
| Vision (optional) | a multimodal model **and its mmproj** projector (KoboldCpp: `"mmproj"` in your `.kcpps`; llama-server: `--mmproj`; Unsloth: switch to a vision model) |

## Installation

```sh
git clone https://github.com/MicroHEROX/Mult-Hands-Eyes-MCP.git
cd Mult-Hands-Eyes-MCP
uv tool install .            # isolated install, no system pollution
multhands --help
```

or from npm (bundles the same Python server; first run creates a private venv and installs two small deps):

```sh
npx mult-hands-eyes-mcp
```

## Configuration

Create `multhands.json` anywhere and point `MULTHANDS_CONFIG` at it (fallback: `multhands.json` in the working directory):

```json
{
  "defaultBackend": "koboldcpp",
  "backends": {
    "koboldcpp": {
      "baseURL": "http://127.0.0.1:5001",
      "model": "koboldcpp",
      "capabilities": ["text", "vision"],
      "timeoutMs": 120000,
      "maxTokens": 8192
    },
    "unsloth": {
      "baseURL": "http://127.0.0.1:8888",
      "model": "unsloth",
      "apiKey": "sk-unsloth-xxxxxxxx",
      "capabilities": ["text", "vision"]
    }
  }
}
```

Quick single-backend alternative: `MULTHANDS_BASE_URL=http://127.0.0.1:5001` (+ optional `MULTHANDS_MODEL`, `MULTHANDS_API_KEY`).

| Field | Meaning |
| --- | --- |
| `baseURL` | service endpoint (required) |
| `model` | wire model id (KoboldCpp & co. ignore it; defaults to the backend name) |
| `apiKey` | for authenticated services (Unsloth: Settings → API) |
| `capabilities` | `"text"` and/or `"vision"` — tools route by capability |
| `timeoutMs` / `maxTokens` | per-call budget (default 120000) / default output cap (default 8192) |
| `defaultBackend` | top-level: backend used when none is named |

## Usage

### `local_run` — text

| Arg | Type | Required | Notes |
| --- | --- | --- | --- |
| `prompt` | string | yes | instruction/text (user message) |
| `system` | string | no | system instruction |
| `backend` | string | no | backend name; default: `defaultBackend` |
| `temperature` | number | no | 0–2 |
| `max_tokens` | integer | no | default: backend `maxTokens` |
| `stop` | string[] | no | stop sequences |

Returns `{ text, reasoning?, model, backend, usage, elapsed_ms }`.

### `local_vision` — OCR / analysis / comparison

| Arg | Type | Required | Notes |
| --- | --- | --- | --- |
| `mode` | `analyze`/`ocr`/`compare` | no | default `analyze` |
| `prompt` | string | no | custom instruction (overrides the mode template) |
| `image_paths` | string[] | no | local absolute paths (png/jpg/jpeg/webp/gif/bmp, ≤ 20 MB each) |
| `image_urls` | string[] | no | `data:` or `http(s)://` URLs |
| `backend` | string | no | backend name (must declare `vision`) |
| `temperature` | number | no | ~0.2 recommended for OCR |
| `max_tokens` | integer | no | output cap |
| `stop` | string[] | no | stop sequences |

Returns `{ text, reasoning?, model, backend, images, usage, elapsed_ms }`. `compare` sends 2–4 images in one request for joint reasoning.

### `local_status` — backends & health

No args. Returns each configured backend with `reachable` (live `GET /v1/models` probe) and a `note` (an `AUTH` note means the server is up but the key was rejected).

## Connect a client

All clients share one premise: `multhands` on PATH (`uv tool install .`), config passed via environment.

<details>
<summary><b>opencode</b> — <code>opencode.json</code></summary>

```json
{
  "mcp": {
    "multhands": {
      "type": "local",
      "command": ["multhands"],
      "enabled": true,
      "environment": { "MULTHANDS_CONFIG": "/path/to/multhands.json" }
    }
  }
}
```

</details>

<details>
<summary><b>Claude Desktop</b> — <code>claude_desktop_config.json</code></summary>

```json
{
  "mcpServers": {
    "multhands": {
      "command": "multhands",
      "env": { "MULTHANDS_CONFIG": "/path/to/multhands.json" }
    }
  }
}
```

</details>

<details>
<summary><b>Cursor</b> — <code>~/.cursor/mcp.json</code></summary>

```json
{
  "mcpServers": {
    "multhands": {
      "command": "multhands",
      "env": { "MULTHANDS_CONFIG": "/path/to/multhands.json" }
    }
  }
}
```

</details>

<details>
<summary><b>Cline</b> — <code>~/.cline_mcp_settings.json</code></summary>

```json
{
  "mcpServers": {
    "multhands": {
      "command": "multhands",
      "env": { "MULTHANDS_CONFIG": "/path/to/multhands.json" }
    }
  }
}
```

</details>

<details>
<summary><b>Windsurf</b> — <code>~/.codeium/windsurf/mcp_config.json</code></summary>

```json
{
  "mcpServers": {
    "multhands": {
      "command": "multhands",
      "env": { "MULTHANDS_CONFIG": "/path/to/multhands.json" }
    }
  }
}
```

</details>

<details>
<summary><b>Cherry Studio / Coco Chat / GUI clients</b></summary>

Add an MCP server of type **Stdio**: command `multhands`, no args, env var `MULTHANDS_CONFIG=<your config path>`.

</details>

<details>
<summary><b>Network mode (Streamable HTTP / SSE)</b> — remote or browser-based clients</summary>

```sh
multhands --transport streamable-http --host 0.0.0.0 --port 8020   # endpoint: http://<host>:8020/mcp
multhands --transport sse --host 0.0.0.0 --port 8021               # endpoint: http://<host>:8021/sse
```

Binds `127.0.0.1` unless you explicitly pass `--host 0.0.0.0`.

</details>

## Uninstall

Clean, zero residue:

1. Remove the `multhands` entry from your client config (other MCP entries are unaffected).
2. `uv tool uninstall multhands-mcp` (or `npm uninstall -g mult-hands-eyes-mcp`).
3. Delete the cloned folder.

The server writes nothing anywhere at runtime, so there is nothing else to clean up.

## Documentation

| Doc | Contents |
| --- | --- |
| [docs/engineering.md](docs/engineering.md) | architecture, tool contracts, commands, test layers |
| [docs/api.md](docs/api.md) | authoritative API reference (config, tools, classes, error codes, CLI, wire contract) |
| [docs/glossary.md](docs/glossary.md) | standard glossary |
| [docs/solutions.md](docs/solutions.md) | pitfalls, troubleshooting, methodology |

> The docs ship with the repository but are intentionally **excluded** from the pip/npm packages.

## Roadmap

**Directions we can go:**

- More vision modes & templates (document layout, table extraction).
- Batch jobs: one agent turn driving many local calls.
- Optional auto-detection of common ports (currently deliberate: explicit config only).
- Publish the Python package to PyPI (`uvx mult-hands-eyes-mcp`).

**Directions we will not go:**

- Becoming an LLM provider adapter — the online model stays the main brain.
- Managing processes — the server remains a pure client; your services are yours.
- Streaming responses — one round trip per tool call is simpler and sufficient.
- Bundling model files (GGUF / mmproj) or modifying any local service.

## Acknowledgments

- **[DeepSeek AI](https://github.com/deepseek-ai)** — the [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness) platform and its plugin patterns shaped this project, via the reference plugins **[dsh-koboldcpp-hands](https://github.com/MicroHEROX/dsh-koboldcpp-hands)** and **[dsh-unsloth-hands](https://github.com/MicroHEROX/dsh-unsloth-hands)** (MIT).
- **[LostRuins / KoboldCpp](https://github.com/LostRuins/koboldcpp)** and **[Unsloth](https://github.com/unslothai/unsloth)** — the local inference servers that make this possible.
- **[llama.cpp](https://github.com/ggml-org/llama.cpp)** and the GGUF quantization ecosystem.
- **[Model Context Protocol](https://modelcontextprotocol.io)** — the protocol and its Python SDK.
- The open models running on your machine.

No affiliation with DeepSeek AI, LostRuins, or Unsloth AI; all trademarks belong to their owners.

## License

[MIT](LICENSE)
