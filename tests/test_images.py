import base64

import httpx
import pytest

from multhands.images import (
    MAX_IMAGE_BYTES,
    ImageError,
    data_url_to_bytes,
    image_to_data_url,
    images_to_data_urls,
    mime_of,
)


@pytest.fixture
def client():
    return httpx.AsyncClient()


PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


def test_mime_of():
    assert mime_of("a.png") == "image/png"
    assert mime_of("A.JPG") == "image/jpeg"
    assert mime_of("x.jpeg") == "image/jpeg"
    assert mime_of("x.webp") == "image/webp"
    assert mime_of("x.gif") == "image/gif"
    assert mime_of("x.bmp") == "image/bmp"


def test_data_url_roundtrip():
    payload = base64.b64encode(PNG_BYTES).decode()
    mime, data = data_url_to_bytes(f"data:image/png;base64,{payload}")
    assert mime == "image/png"
    assert data == PNG_BYTES


def test_data_url_rejects_non_base64():
    with pytest.raises(ImageError):
        data_url_to_bytes("data:image/png,rawbytes!")


def test_data_url_rejects_garbage():
    with pytest.raises(ImageError):
        data_url_to_bytes("not a data url")
    with pytest.raises(ImageError):
        data_url_to_bytes("data:image/png;base64,!!!notb64!!!")


async def test_data_url_passthrough(client):
    payload = base64.b64encode(PNG_BYTES).decode()
    result = await image_to_data_url(f"data:image/png;base64,{payload}", client, 5000)
    assert result.startswith("data:image/png;base64,")


async def test_local_path(tmp_path, client):
    path = tmp_path / "shot.png"
    path.write_bytes(PNG_BYTES)
    result = await image_to_data_url(str(path), client, 5000)
    assert result.startswith("data:image/png;base64,")


async def test_local_path_missing(client):
    with pytest.raises(ImageError, match="not found"):
        await image_to_data_url(r"C:\does\not\exist.png", client, 5000)


async def test_local_path_unsupported_mime(tmp_path, client):
    path = tmp_path / "doc.txt"
    path.write_text("hello")
    with pytest.raises(ImageError, match="mime"):
        await image_to_data_url(str(path), client, 5000)


async def test_http_url_fetch(tmp_path, client):
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=PNG_BYTES, headers={"content-type": "image/png"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    result = await image_to_data_url("https://example.com/shot.png", client, 5000)
    assert result.startswith("data:image/png;base64,")


async def test_http_url_error(client):
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    with pytest.raises(httpx.HTTPStatusError):
        await image_to_data_url("https://example.com/missing.png", client, 5000)


async def test_size_limit(client):
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, content=b"\x00" * (MAX_IMAGE_BYTES + 1), headers={"content-type": "image/png"}
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    with pytest.raises(ImageError, match="limit"):
        await image_to_data_url("https://example.com/big.png", client, 5000)


async def test_empty_source(client):
    with pytest.raises(ImageError, match="empty"):
        await image_to_data_url("   ", client, 5000)


async def test_images_to_data_urls_mix(tmp_path, client):
    path = tmp_path / "a.png"
    path.write_bytes(PNG_BYTES)
    payload = base64.b64encode(PNG_BYTES).decode()
    results = await images_to_data_urls(
        [str(path), f"data:image/png;base64,{payload}"], client, 5000
    )
    assert len(results) == 2
    assert all(r.startswith("data:image/png;base64,") for r in results)