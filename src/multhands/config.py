"""Configuration loading for Multhands: multiple OpenAI-compatible local
backends (KoboldCpp, Unsloth Desktop, llama.cpp server, LM Studio, Ollama,
text-generation-webui, ...), each with an optional capability set
(`text` / `vision`).

Two configuration channels, merged in order:

1. A JSON config file pointed at by the `MULTHANDS_CONFIG` environment
   variable (falls back to `multhands.json` in the current directory).
   The file is re-read and re-parsed on every call, so backends can be
   edited without restarting the MCP server (hot reload).

2. Environment variables only — a single quick backend:
   `MULTHANDS_BASE_URL` (required), `MULTHANDS_MODEL`, `MULTHANDS_API_KEY`.

Nothing here talks to the network; it only resolves which endpoint to call.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

CONFIG_ENV = "MULTHANDS_CONFIG"
BASE_URL_ENV = "MULTHANDS_BASE_URL"
MODEL_ENV = "MULTHANDS_MODEL"
API_KEY_ENV = "MULTHANDS_API_KEY"

DEFAULT_CONFIG_FILENAME = "multhands.json"
DEFAULT_TIMEOUT_MS = 120_000
DEFAULT_MAX_TOKENS = 8_192

#: Valid capability names a backend can declare.
CAPABILITIES = ("text", "vision")


class ConfigError(Exception):
    """Raised for invalid configuration; surfaced to the model as a tool error."""


@dataclass
class Backend:
    """One local inference endpoint."""

    name: str
    base_url: str
    model: str
    api_key: Optional[str] = None
    capabilities: list[str] = field(default_factory=lambda: ["text", "vision"])
    timeout_ms: int = DEFAULT_TIMEOUT_MS
    max_tokens: int = DEFAULT_MAX_TOKENS

    def has(self, capability: str) -> bool:
        return capability in self.capabilities


@dataclass
class Config:
    """The resolved whole configuration."""

    backends: dict[str, Backend]
    default_backend: Optional[str] = None
    source: str = "environment"

    @property
    def names(self) -> list[str]:
        return list(self.backends.keys())

    def get(self, name: Optional[str], capability: str) -> Backend:
        """Resolve one backend for a call, honoring the capability.

        Precedence: explicit `name` → default backend → the only backend.
        Raises ConfigError with an actionable message when nothing fits.
        """
        if name is not None:
            backend = self.backends.get(name)
            if backend is None:
                raise ConfigError(
                    f"backend {name!r} is not configured. "
                    f"Configured backends: {', '.join(self.names) or '(none)'}"
                )
            if not backend.has(capability):
                raise ConfigError(
                    f"backend {name!r} does not declare capability "
                    f"{capability!r}; it has {sorted(backend.capabilities)!r}. "
                    f"Pick a backend with {capability!r}, or fix its "
                    f"`capabilities` list in the config."
                )
            return backend

        if self.default_backend is not None:
            backend = self.backends.get(self.default_backend)
            if backend is None:
                raise ConfigError(
                    f"default backend {self.default_backend!r} is not defined "
                    f"in the backends map. Configured backends: "
                    f"{', '.join(self.names) or '(none)'}"
                )
            if not backend.has(capability):
                raise ConfigError(
                    f"default backend {backend.name!r} does not declare "
                    f"capability {capability!r}; it has "
                    f"{sorted(backend.capabilities)!r}. Pass `backend` "
                    f"explicitly, or fix its `capabilities` list in the config."
                )
            return backend

        candidates = [b for b in self.backends.values() if b.has(capability)]
        if len(candidates) == 1:
            return candidates[0]
        if not candidates:
            raise ConfigError(
                f"no backend declares capability {capability!r}. Configured "
                f"backends: {', '.join(self.names) or '(none)'}"
            )
        raise ConfigError(
            f"multiple backends declare capability {capability!r} "
            f"({', '.join(b.name for b in candidates)}) and no default "
            f"backend is set; pass `backend` explicitly or set "
            f"`defaultBackend` in the config."
        )


def _env_backend() -> Optional[Backend]:
    base_url = os.environ.get(BASE_URL_ENV)
    if not base_url:
        return None
    model = os.environ.get(MODEL_ENV) or "local"
    api_key = os.environ.get(API_KEY_ENV)
    return Backend(name="env", base_url=base_url, model=model, api_key=api_key)


def _config_path() -> Optional[Path]:
    env = os.environ.get(CONFIG_ENV)
    if env:
        return Path(env)
    cwd = Path.cwd() / DEFAULT_CONFIG_FILENAME
    if cwd.is_file():
        return cwd
    return None


def _from_file(path: Path) -> Config:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ConfigError(f"cannot read config file {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(f"config file {path} is not valid JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise ConfigError(f"config file {path} must contain a JSON object")

    raw_backends = data.get("backends")
    if raw_backends is None:
        raise ConfigError(
            f"config file {path} has no `backends` object; expected shape: "
            '{"backends": {"<name>": {"baseURL": "...", "model": "..."}}, '
            '"defaultBackend": "<name>"}'
        )
    if not isinstance(raw_backends, dict) or not raw_backends:
        raise ConfigError(f"`backends` in {path} must be a non-empty object")

    backends: dict[str, Backend] = {}
    for name, raw in raw_backends.items():
        if not isinstance(raw, dict):
            raise ConfigError(f"backend {name!r} in {path} must be an object")
        base_url = raw.get("baseURL") or raw.get("base_url")
        if not isinstance(base_url, str) or not base_url:
            raise ConfigError(
                f"backend {name!r} in {path} needs a `baseURL` string"
            )
        model = raw.get("model", name)
        if not isinstance(model, str) or not model:
            raise ConfigError(f"backend {name!r} in {path}: `model` must be a string")

        api_key = raw.get("apiKey") or raw.get("api_key") or None
        if api_key is not None and not isinstance(api_key, str):
            raise ConfigError(f"backend {name!r} in {path}: `apiKey` must be a string")

        capabilities = raw.get("capabilities", ["text", "vision"])
        if not isinstance(capabilities, list) or not all(
            isinstance(c, str) for c in capabilities
        ):
            raise ConfigError(
                f"backend {name!r} in {path}: `capabilities` must be a list "
                "of strings"
            )
        unknown = set(capabilities) - set(CAPABILITIES)
        if unknown:
            raise ConfigError(
                f"backend {name!r} in {path}: unknown capabilities "
                f"{sorted(unknown)!r}; valid ones are {list(CAPABILITIES)!r}"
            )

        timeout_ms = raw.get("timeoutMs", DEFAULT_TIMEOUT_MS)
        max_tokens = raw.get("maxTokens", DEFAULT_MAX_TOKENS)
        if not isinstance(timeout_ms, int) or timeout_ms <= 0:
            raise ConfigError(f"backend {name!r} in {path}: `timeoutMs` must be a positive integer")
        if not isinstance(max_tokens, int) or max_tokens <= 0:
            raise ConfigError(f"backend {name!r} in {path}: `maxTokens` must be a positive integer")

        backends[name] = Backend(
            name=name,
            base_url=base_url.rstrip("/"),
            model=model,
            api_key=api_key,
            capabilities=list(dict.fromkeys(capabilities)),
            timeout_ms=timeout_ms,
            max_tokens=max_tokens,
        )

    default_backend = data.get("defaultBackend")
    if default_backend is not None and not isinstance(default_backend, str):
        raise ConfigError(f"`defaultBackend` in {path} must be a string")

    return Config(
        backends=backends,
        default_backend=default_backend,
        source=str(path),
    )


def _from_env() -> Config:
    backend = _env_backend()
    if backend is None:
        raise ConfigError(
            "multhands is not configured. Either set MULTHANDS_CONFIG to a "
            "JSON config file, put a `multhands.json` in the working "
            "directory, or set MULTHANDS_BASE_URL (plus optional "
            "MULTHANDS_MODEL / MULTHANDS_API_KEY) for a single quick backend."
        )
    return Config(backends={backend.name: backend}, default_backend="env")


def load_config() -> Config:
    """Load the configuration from the best available channel."""
    path = _config_path()
    if path is not None:
        return _from_file(path)
    return _from_env()


class ConfigSource:
    """Reloading config handle.

    File-based configs are re-read and re-parsed on EVERY call (config files
    are a few KB, so this is cheap) — Windows filesystem timestamps are too
    coarse for reliable mtime-based caching, and re-reading makes hot reload
    trivially correct. If the file is temporarily unreadable/invalid (e.g.
    mid-edit), the last good config is served instead. Env-based configs are
    re-read on every call too.
    """

    def __init__(self) -> None:
        self._path = _config_path()
        self._last_good: Optional[Config] = None

    def get(self) -> Config:
        if self._path is not None:
            try:
                config = _from_file(self._path)
            except ConfigError:
                if self._last_good is not None:
                    return self._last_good
                raise
            self._last_good = config
            return config
        return load_config()


def describe_backends(config: Config) -> Iterable[str]:
    """One human line per backend, for `local_status` output."""
    for name in config.names:
        backend = config.backends[name]
        yield (
            f"- {name}: {backend.base_url} (model={backend.model!r}, "
            f"capabilities={sorted(backend.capabilities)!r})"
        )
