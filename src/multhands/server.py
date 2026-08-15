"""Multhands MCP server: gives an online LLM (opencode, Claude Desktop, any
MCP client) a pair of LOCAL hands.

The main conversation model stays wherever the deployment puts it; when it
wants cheap, repetitive, token-wasting labor done — batch rewrites, name
translations, string munging, deduplication, short summaries, structured
extraction, and especially vision work (OCR / image analysis / image
comparison) for non-multimodal main models — it calls `local_run` or
`local_vision` and a local OpenAI-compatible server (KoboldCpp, Unsloth,
llama.cpp server, LM Studio, Ollama /v1, ...) does the work.

Backends are EXPLICITLY configured by the user (config file / env vars):
the server never scans ports or auto-detects services. It is a PURE CLIENT:
it never starts, owns, or stops any process, and never writes any file.

MCP compliance notes:
- Errors are raised as exceptions, so tool failures surface as
  `CallToolResult.isError: true` on the wire (MCP spec), with the stable
  code and hint inside the message text.
- Success results are JSON objects; the SDK emits them as text content
  (plus structured content, which the spec allows as optional).
"""

from __future__ import annotations

import time
from typing import Annotated, NoReturn, Optional

import httpx
from mcp.server.mcpserver import MCPServer
from pydantic import Field

from . import __version__
from .client import LocalError, chat_completion, probe
from .config import ConfigError, ConfigSource
from .errors import LocalCallError
from .images import ImageError, images_to_data_urls
from .prompts import VALID_MODES, VISION_FIDELITY_RULE, resolve_vision_prompt

SERVER_INSTRUCTIONS = (
    "You have local hands: OpenAI-compatible local inference services "
    "(KoboldCpp, Unsloth Desktop, llama.cpp server, LM Studio, Ollama, ...) "
    "running on this machine. Use them for cheap, repetitive, token-wasting "
    "labor and ALL vision work:\n"
    "- `local_run`: one prompt on a local TEXT model — batch rewrites, name "
    "translations, string munging, deduplication, short summaries, "
    "structured extraction, other mechanical text work.\n"
    "- `local_vision`: images to a local MULTIMODAL model — OCR, image "
    "analysis, multi-image comparison. Main models without vision use this "
    "for every image task.\n"
    "- `local_status`: list configured backends and their health.\n\n"
    "Offload eagerly: anything mechanical, repetitive, or visual goes local "
    "first. Use your own tokens only for reasoning, decisions, and the final "
    "answer.\n"
    + VISION_FIDELITY_RULE
)

LOCAL_RUN_DESCRIPTION = (
    "Run ONE prompt on a LOCAL OpenAI-compatible text model on this machine "
    "(KoboldCpp / Unsloth / llama.cpp / LM Studio / Ollama ...).\n\n"
    "Use it for simple, repetitive, token-cheap labor instead of spending "
    "main-model tokens: batch rewrites, name translations, string munging, "
    "deduplication, short-text summarization, structured extraction, and "
    "other mechanical text work. The prompt is sent to the local model as a "
    "user message (the server applies its own chat template)."
)

LOCAL_VISION_DESCRIPTION = (
    "Send one or more images to a LOCAL multimodal model (KoboldCpp / "
    "Unsloth / llama.cpp with an mmproj projector, ...) for image "
    "understanding: OCR / text extraction, describing or analyzing images, "
    "reading charts and screenshots, comparing images.\n\n"
    "Use it to offload vision work from the main model — especially when the "
    "main model is text-only and cannot see images itself: pass the image "
    "path (or a data:/http(s) URL) in image_paths / image_urls and the local "
    "vision model reads it.\n\n"
    "Images come from local file paths (image_paths), data:/http(s) image "
    "URLs (image_urls), or both. png/jpg/jpeg/webp/gif/bmp, up to 20 MB "
    "each. The local server must run a multimodal model with its mmproj "
    "projector loaded.\n\n"
    "Pick a mode for structured output, or pass your own prompt for a "
    "specific question (never both):\n"
    "- `analyze` (default): an '# Image Analysis Report' with 8 fixed "
    "sections: Summary / Image Metadata / Layout & Composition / Visible "
    "Text (VERBATIM) / Objects & Elements / People & Actions / Semantic "
    "Context & Inferences / Uncertainties & Gaps.\n"
    "- `ocr`: character-exact text extraction in reading order (the model "
    "does NOT 'fix' typos or drop symbols; unresolvable glyphs are noted).\n"
    "- `compare`: with 2-4 images in ONE call, an '# Image Comparison "
    "Report': Per-Image Summaries / Common Elements / Key Differences / "
    "Text Differences (VERBATIM) / Overall Conclusion.\n"
    "For independent per-image analysis use one call per image; use "
    "`compare` only when the task needs joint reasoning across images.\n\n"
    "The local model may also return reasoning text (thinking) before its "
    "answer; it is reported separately as `reasoning`.\n"
    + VISION_FIDELITY_RULE
)

mcp = MCPServer(
    "multhands",
    version=__version__,
    instructions=SERVER_INSTRUCTIONS,
)

config_source = ConfigSource()
_client: Optional[httpx.AsyncClient] = None


def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient()
    return _client


def _elapsed(started: float) -> int:
    return int((time.monotonic() - started) * 1000)


def _usage_dict(prompt_tokens: int, completion_tokens: int) -> dict:
    return {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens}


def _raise_config(exc: ConfigError) -> NoReturn:
    raise LocalCallError(str(exc), "MISCONFIGURED") from exc


def _raise_local(exc: LocalError) -> NoReturn:
    raise LocalCallError(str(exc), exc.code) from exc


def _raise_image(exc: ImageError) -> NoReturn:
    raise LocalCallError(str(exc), "INVALID_REQUEST") from exc


@mcp.tool(description=LOCAL_RUN_DESCRIPTION)
async def local_run(
    prompt: Annotated[str, Field(description="The instruction or text to send to the local model (a user-role message).")],
    system: Annotated[Optional[str], Field(description="Optional system instruction prepended to the prompt.")] = None,
    backend: Annotated[Optional[str], Field(description="Name of the configured backend to use. Omit to use the default (or the only one). See `local_status` for configured backends and which support text.")] = None,
    temperature: Annotated[Optional[float], Field(description="Sampling temperature (0-2). Lower values are more deterministic.")] = None,
    max_tokens: Annotated[Optional[int], Field(description="Maximum number of tokens the local model may generate; defaults to the backend's configured cap.")] = None,
    stop: Annotated[Optional[list[str]], Field(description="Stop sequences; generation halts at the first occurrence.")] = None,
) -> dict:
    """Run one prompt on the local text backend."""
    started = time.monotonic()
    try:
        config = config_source.get()
        chosen = config.get(backend, "text")
    except ConfigError as exc:
        _raise_config(exc)

    try:
        completion = await chat_completion(
            get_client(),
            chosen,
            prompt=prompt,
            system=system,
            temperature=temperature,
            max_tokens=max_tokens,
            stop=stop,
        )
    except LocalError as exc:
        _raise_local(exc)

    return {
        "text": completion.text,
        **({"reasoning": completion.reasoning} if completion.reasoning else {}),
        "model": completion.model,
        "backend": chosen.name,
        "usage": _usage_dict(completion.prompt_tokens, completion.completion_tokens),
        "elapsed_ms": _elapsed(started),
    }


@mcp.tool(description=LOCAL_VISION_DESCRIPTION)
async def local_vision(
    mode: Annotated[str, Field(description="Built-in prompt template: analyze (structured 8-section report), ocr (verbatim text extraction), compare (multi-image 5-section report). Ignored when a custom prompt is given.")] = "analyze",
    prompt: Annotated[Optional[str], Field(description="Custom instruction for the local vision model; omit it to use the mode template.")] = None,
    image_paths: Annotated[Optional[list[str]], Field(description="Absolute paths of local image files (png/jpg/jpeg/webp/gif/bmp, up to 20 MB each).")] = None,
    image_urls: Annotated[Optional[list[str]], Field(description="Image URLs: data:image/... or http(s):// URLs.")] = None,
    backend: Annotated[Optional[str], Field(description="Name of the configured backend to use. Omit to use the default (or the only one). See `local_status` for configured backends and which support vision.")] = None,
    temperature: Annotated[Optional[float], Field(description="Sampling temperature (0-2). Lower values are more deterministic — use ~0.2 for OCR.")] = None,
    max_tokens: Annotated[Optional[int], Field(description="Maximum number of tokens the local model may generate; defaults to the backend's configured cap.")] = None,
    stop: Annotated[Optional[list[str]], Field(description="Stop sequences; generation halts at the first occurrence.")] = None,
) -> dict:
    """Send images to the local multimodal backend."""
    started = time.monotonic()
    if mode not in VALID_MODES:
        raise LocalCallError(
            f"unknown mode {mode!r}; valid modes: {', '.join(VALID_MODES)}",
            "INVALID_REQUEST",
        )
    try:
        config = config_source.get()
        chosen = config.get(backend, "vision")
    except ConfigError as exc:
        _raise_config(exc)

    sources = (image_paths or []) + (image_urls or [])
    if not sources:
        raise LocalCallError(
            "no images to analyze: provide image_paths (local files) or "
            "image_urls (data:/http(s) URLs), or both",
            "INVALID_REQUEST",
        )
    if mode == "compare" and not 2 <= len(sources) <= 4:
        raise LocalCallError(
            f"compare needs 2-4 images in one call, got {len(sources)}; "
            "use analyze (one call per image) instead, or pass 2-4 images",
            "INVALID_REQUEST",
        )

    try:
        images = await images_to_data_urls(
            sources,
            get_client(),
            timeout_ms=chosen.timeout_ms,
        )
    except ImageError as exc:
        _raise_image(exc)

    try:
        completion = await chat_completion(
            get_client(),
            chosen,
            prompt=resolve_vision_prompt(mode, prompt),
            images=images,
            temperature=temperature,
            max_tokens=max_tokens,
            stop=stop,
        )
    except LocalError as exc:
        _raise_local(exc)

    return {
        "text": completion.text,
        **({"reasoning": completion.reasoning} if completion.reasoning else {}),
        "model": completion.model,
        "backend": chosen.name,
        "images": len(images),
        "usage": _usage_dict(completion.prompt_tokens, completion.completion_tokens),
        "elapsed_ms": _elapsed(started),
    }


@mcp.tool()
async def local_status() -> dict:
    """List all configured local backends and probe their health.

    Use this when unsure which local services are available, which names to
    pass as `backend`, or whether a server is up. One HTTP probe per backend;
    a "not reachable" result usually means the local service is not running.
    """
    try:
        config = config_source.get()
    except ConfigError as exc:
        _raise_config(exc)

    results = []
    client = get_client()
    for name in config.names:
        backend = config.backends[name]
        reachable, note = await probe(client, backend)
        results.append(
            {
                "name": name,
                "baseURL": backend.base_url,
                "model": backend.model,
                "capabilities": sorted(backend.capabilities),
                "reachable": reachable,
                "note": note,
            }
        )

    return {
        "default_backend": config.default_backend,
        "config_source": config.source,
        "backends": results,
    }


def parse_args(argv=None):
    """CLI arguments for the transport. Zero-arg invocation = stdio, which
    is what every stdio-based MCP client (opencode, Claude Desktop, Cursor,
    Cline, Windsurf, ...) launches."""
    import argparse

    parser = argparse.ArgumentParser(
        prog="multhands",
        description=(
            "Multhands MCP server: local hands (text + vision) for online "
            "LLMs via OpenAI-compatible local inference services."
        ),
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse", "streamable-http"],
        default="stdio",
        help="MCP transport (default: stdio). Use sse or streamable-http to "
        "serve remote/browser-based clients over the network.",
    )
    parser.add_argument("--host", default="127.0.0.1", help="bind host for sse/streamable-http")
    parser.add_argument("--port", type=int, default=8000, help="bind port for sse/streamable-http")
    return parser.parse_args(argv)


def main() -> None:
    args = parse_args()
    if args.transport == "stdio":
        mcp.run(transport="stdio")
    else:
        mcp.run(transport=args.transport, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
