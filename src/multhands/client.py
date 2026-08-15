"""OpenAI-compatible chat-completions client for local inference servers
(KoboldCpp, Unsloth Desktop, llama.cpp server, LM Studio, Ollama /v1, ...):
one non-streaming `POST {baseURL}/v1/chat/completions` per call, with
friendly, actionable error mapping so the online model sees clean failure
messages instead of raw network noise.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Optional

import httpx

from .config import Backend

#: Stable error codes surfaced in tool failure messages.
ERROR_CODES = (
    "SERVER_NOT_RUNNING",
    "TRANSPORT",
    "TIMEOUT",
    "AUTH",
    "RATE_LIMIT",
    "CONTEXT_WINDOW_EXCEEDED",
    "INVALID_REQUEST",
    "SERVER",
    "EMPTY_RESPONSE",
)

#: Keyword fragments that mark a 400 as a context-window failure.
CONTEXT_WINDOW_MARKERS = (
    "context",
    "exceed",
    "max context",
    "n_ctx",
    "window",
    "truncat",
    "too long",
)


class LocalError(Exception):
    """One failed local call, with a stable code and an actionable hint."""

    def __init__(self, message: str, code: str, hint: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.hint = hint

    def __str__(self) -> str:
        text = f"[{self.code}] {self.message}"
        if self.hint:
            text += f"\nHint: {self.hint}"
        return text


@dataclass
class ChatCompletion:
    """The completed local-model answer."""

    text: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    reasoning: Optional[str] = None


def _estimate_tokens(chars: int) -> int:
    """Coarse token estimate (~4 chars/token), used only when the server
    omits usage."""
    return max(1, -(-max(0, chars) // 4))


def _hint_for(code: str) -> str | None:
    return {
        "SERVER_NOT_RUNNING": (
            "the local inference server is not answering; start it first "
            "(e.g. launch KoboldCpp, Unsloth Desktop, llama-server or LM "
            "Studio with a model loaded) and make sure `baseURL` matches its port"
        ),
        "TIMEOUT": (
            "the local model is too slow for the current budget; raise "
            "`timeoutMs` for this backend in the config, or use a smaller/faster model"
        ),
        "AUTH": (
            "the server rejected the request as unauthorized; set the right "
            "`apiKey` for this backend in the config (for Unsloth: Settings -> "
            "API -> Create)"
        ),
        "CONTEXT_WINDOW_EXCEEDED": (
            "the local model's context window is too small for this request; "
            "shorten the input, drop images, or load a model with a bigger context"
        ),
        "EMPTY_RESPONSE": (
            "the local model produced no text; it may not support the request "
            "(for vision calls, check that the loaded model is multimodal and "
            "its mmproj projector is loaded)"
        ),
    }.get(code)


def _map_http_error(
    status: int,
    backend: Backend,
    error_body: str,
) -> LocalError:
    detail = error_body[:500]
    if status in (401, 403):
        return LocalError(
            f"{backend.name}: request rejected (HTTP {status})",
            "AUTH",
            _hint_for("AUTH"),
        )
    if status == 429:
        return LocalError(f"{backend.name}: rate limited (HTTP 429)", "RATE_LIMIT")
    if status == 400:
        lowered = detail.lower()
        if any(marker in lowered for marker in CONTEXT_WINDOW_MARKERS):
            return LocalError(
                f"{backend.name}: context window exceeded (HTTP 400)"
                + (f"; {detail}" if detail else ""),
                "CONTEXT_WINDOW_EXCEEDED",
                _hint_for("CONTEXT_WINDOW_EXCEEDED"),
            )
        return LocalError(
            f"{backend.name}: invalid request (HTTP 400)"
            + (f"; {detail}" if detail else ""),
            "INVALID_REQUEST",
        )
    if status >= 500:
        return LocalError(
            f"{backend.name}: server error (HTTP {status})"
            + (f"; {detail}" if detail else ""),
            "SERVER",
        )
    return LocalError(f"{backend.name}: HTTP {status}" + (f"; {detail}" if detail else ""), f"HTTP_{status}")


def _build_messages(
    prompt: str,
    system: str | None,
    images: list[str] | None,
) -> list[dict]:
    messages: list[dict] = []
    if system:
        messages.append({"role": "system", "content": system})
    if images:
        content: list[dict] = [{"type": "text", "text": prompt}]
        content.extend({"type": "image_url", "image_url": {"url": image}} for image in images)
        messages.append({"role": "user", "content": content})
    else:
        messages.append({"role": "user", "content": prompt})
    return messages


async def chat_completion(
    client: httpx.AsyncClient,
    backend: Backend,
    *,
    prompt: str,
    system: str | None = None,
    images: list[str] | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    stop: list[str] | None = None,
) -> ChatCompletion:
    """Run one non-streaming local completion.

    Raises LocalError with codes: SERVER_NOT_RUNNING / TRANSPORT / TIMEOUT /
    AUTH / RATE_LIMIT / CONTEXT_WINDOW_EXCEEDED / INVALID_REQUEST /
    SERVER / EMPTY_RESPONSE / HTTP_<n>.
    """
    payload: dict = {
        "model": backend.model,
        "messages": _build_messages(prompt, system, images),
    }
    if temperature is not None:
        payload["temperature"] = temperature
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens
    elif backend.max_tokens:
        payload["max_tokens"] = backend.max_tokens
    if stop:
        payload["stop"] = stop

    headers = {"content-type": "application/json", "accept": "application/json"}
    if backend.api_key:
        headers["authorization"] = f"Bearer {backend.api_key}"

    url = f"{backend.base_url}/v1/chat/completions"
    try:
        response = await client.post(
            url,
            headers=headers,
            content=json.dumps(payload),
            timeout=backend.timeout_ms / 1000,
        )
    except httpx.ConnectError as exc:
        raise LocalError(
            f"{backend.name}: cannot reach the server at {backend.base_url}",
            "SERVER_NOT_RUNNING",
            _hint_for("SERVER_NOT_RUNNING"),
        ) from exc
    except httpx.ConnectTimeout as exc:
        raise LocalError(
            f"{backend.name}: connection to {backend.base_url} timed out "
            "(server may still be loading the model)",
            "SERVER_NOT_RUNNING",
            _hint_for("SERVER_NOT_RUNNING"),
        ) from exc
    except httpx.TimeoutException as exc:
        raise LocalError(
            f"{backend.name}: call timed out after {backend.timeout_ms} ms",
            "TIMEOUT",
            _hint_for("TIMEOUT"),
        ) from exc
    except httpx.HTTPError as exc:
        raise LocalError(
            f"{backend.name}: request to {backend.base_url} failed: {exc}",
            "TRANSPORT",
        ) from exc

    if response.status_code != 200:
        body = response.text
        raise _map_http_error(response.status_code, backend, body)

    try:
        parsed = response.json()
    except ValueError as exc:
        raise LocalError(
            f"{backend.name}: returned a malformed (non-JSON) response",
            "INVALID_REQUEST",
        ) from exc

    message = (
        parsed.get("choices") or [{}]
    )[0].get("message") or {}
    content = message.get("content")
    if isinstance(content, list):
        content = "".join(
            part.get("text", "")
            for part in content
            if isinstance(part, dict) and part.get("type") == "text"
        )
    text = (content or "").strip()
    if not text:
        raise LocalError(
            f"{backend.name}: the local model returned an empty response",
            "EMPTY_RESPONSE",
            _hint_for("EMPTY_RESPONSE"),
        )

    reasoning = message.get("reasoning_content") or message.get("reasoning")
    usage = parsed.get("usage") or {}
    prompt_tokens = usage.get("prompt_tokens")
    completion_tokens = usage.get("completion_tokens")
    if not isinstance(prompt_tokens, int) or prompt_tokens < 0:
        prompt_tokens = _estimate_tokens(len(json.dumps(payload, ensure_ascii=False)))
    if not isinstance(completion_tokens, int) or completion_tokens < 0:
        completion_tokens = _estimate_tokens(len(text))

    return ChatCompletion(
        text=text,
        model=parsed.get("model") or backend.model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        reasoning=reasoning if isinstance(reasoning, str) and reasoning.strip() else None,
    )


async def probe(
    client: httpx.AsyncClient,
    backend: Backend,
) -> tuple[bool, str]:
    """Health-probe one backend via GET /v1/models.

    Returns (reachable, note). 401/403 count as reachable — the server is
    running, only the key is wrong (the call itself will say so).
    """
    headers = {"accept": "application/json"}
    if backend.api_key:
        headers["authorization"] = f"Bearer {backend.api_key}"
    try:
        response = await client.get(
            f"{backend.base_url}/v1/models",
            headers=headers,
            timeout=min(backend.timeout_ms, 10_000) / 1000,
        )
    except httpx.HTTPError:
        return False, "not reachable"
    if response.status_code in (401, 403):
        return True, "reachable but key rejected (AUTH)"
    if 200 <= response.status_code < 300:
        return True, "ok"
    return True, f"reachable (HTTP {response.status_code})"
