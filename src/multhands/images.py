"""Image ingestion for the vision tool: turn every supported image source
into a `data:image/...;base64,...` URL for the local multimodal model.

Supported sources (in any mix):

- local file paths (any path the MCP server process can read),
- `data:image/...` URLs (validated and size-checked),
- `http(s)://` URLs (downloaded by the MCP server and re-encoded as data
  URLs, so the local model never needs internet access itself).
"""

from __future__ import annotations

import base64
import binascii
import mimetypes
from pathlib import Path

import httpx

#: Hard size cap per image (bytes). Small local GGUF servers choke on huge blobs.
MAX_IMAGE_BYTES = 20 * 1024 * 1024

#: Image mime types this tool accepts; everything else is rejected early.
SUPPORTED_MIMES = {
    "image/png",
    "image/jpeg",
    "image/webp",
    "image/gif",
    "image/bmp",
}

EXTENSION_MIMES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
}


class ImageError(Exception):
    """Raised when an image source cannot be turned into a data URL."""


def _check_size(length: int, source: str) -> None:
    if length > MAX_IMAGE_BYTES:
        raise ImageError(
            f"image {source!r} is {length / (1024 * 1024):.1f} MB, above the "
            f"{MAX_IMAGE_BYTES // (1024 * 1024)} MB per-image limit"
        )


def _encode(mime: str, payload: bytes, source: str) -> str:
    if mime not in SUPPORTED_MIMES:
        raise ImageError(
            f"image {source!r} has mime {mime!r}; supported: "
            f"{', '.join(sorted(SUPPORTED_MIMES))}"
        )
    _check_size(len(payload), source)
    return f"data:{mime};base64,{base64.b64encode(payload).decode('ascii')}"


def mime_of(path: str | Path) -> str:
    """Guess the image mime type from a file path/extension."""
    suffix = Path(path).suffix.lower()
    if suffix in EXTENSION_MIMES:
        return EXTENSION_MIMES[suffix]
    guessed, _ = mimetypes.guess_type(str(path))
    return guessed or "image/png"


def data_url_to_bytes(url: str) -> tuple[str, bytes]:
    """Parse a data URL into (mime, payload); raises ImageError on garbage."""
    try:
        header, b64 = url.split(",", 1)
    except ValueError:
        raise ImageError(f"malformed data: URL (no comma): {url[:80]!r}...") from None
    if not header.startswith("data:"):
        raise ImageError(f"malformed data: URL (missing data: prefix): {header[:80]!r}")
    meta = header[len("data:"):]
    mime = "image/png"
    if ";" in meta:
        mime_part, params = meta.split(";", 1)
        mime = mime_part or mime
        if "base64" not in params.split(";"):
            raise ImageError("only base64-encoded data: URLs are supported")
    try:
        payload = base64.b64decode(b64, validate=True)
    except binascii.Error:
        raise ImageError("malformed base64 payload in data: URL") from None
    if not payload:
        raise ImageError("empty image payload")
    return mime, payload


async def image_to_data_url(
    source: str,
    client: httpx.AsyncClient,
    timeout_ms: int,
) -> str:
    """Convert one image source (path / data URL / http(s) URL) to a data URL.

    `client` and `timeout_ms` are used only for http(s) sources.
    """
    source = source.strip()
    if not source:
        raise ImageError("empty image source")

    if source.startswith("data:"):
        mime, payload = data_url_to_bytes(source)
        return _encode(mime, payload, source[:64])

    if source.startswith("http://") or source.startswith("https://"):
        response = await client.get(
            source,
            timeout=timeout_ms / 1000,
            follow_redirects=True,
        )
        response.raise_for_status()
        content_type = response.headers.get("content-type", "").split(";")[0].strip()
        payload = response.content
        if not payload:
            raise ImageError(f"image URL {source!r} returned an empty body")
        mime = content_type or mime_of(source.split("?", 1)[0])
        return _encode(mime, payload, source[:64])

    path = Path(source)
    if not path.is_file():
        raise ImageError(f"image file not found: {source!r}")
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise ImageError(f"cannot read image file {source!r}: {exc}") from exc
    if not payload:
        raise ImageError(f"image file {source!r} is empty")
    return _encode(mime_of(path), payload, source)


async def images_to_data_urls(
    sources: list[str],
    client: httpx.AsyncClient,
    timeout_ms: int,
) -> list[str]:
    """Convert a list of image sources; raises ImageError with the source."""
    return [
        await image_to_data_url(source, client, timeout_ms)
        for source in sources
    ]
