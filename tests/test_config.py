import json

import pytest

from multhands.config import (
    BASE_URL_ENV,
    ConfigError,
    ConfigSource,
    _from_env,
    _from_file,
)


def write_config(tmp_path, data, name="multhands.json"):
    path = tmp_path / name
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_from_file_basic(tmp_path):
    path = write_config(
        tmp_path,
        {
            "defaultBackend": "koboldcpp",
            "backends": {
                "koboldcpp": {"baseURL": "http://127.0.0.1:5001"},
                "unsloth": {"baseURL": "http://127.0.0.1:8888", "apiKey": "sk-x"},
            },
        },
    )
    config = _from_file(path)
    assert config.names == ["koboldcpp", "unsloth"]
    assert config.default_backend == "koboldcpp"
    assert config.backends["koboldcpp"].model == "koboldcpp"
    assert config.backends["koboldcpp"].capabilities == ["text", "vision"]
    assert config.backends["koboldcpp"].timeout_ms == 120_000
    assert config.backends["unsloth"].api_key == "sk-x"


def test_from_file_base_url_trailing_slash(tmp_path):
    path = write_config(tmp_path, {"backends": {"a": {"baseURL": "http://127.0.0.1:5001/"}}})
    assert _from_file(path).backends["a"].base_url == "http://127.0.0.1:5001"


def test_from_file_missing_backends(tmp_path):
    path = write_config(tmp_path, {})
    with pytest.raises(ConfigError, match="backends"):
        _from_file(path)


def test_from_file_empty_backends(tmp_path):
    path = write_config(tmp_path, {"backends": {}})
    with pytest.raises(ConfigError, match="non-empty"):
        _from_file(path)


def test_from_file_no_base_url(tmp_path):
    path = write_config(tmp_path, {"backends": {"a": {"model": "x"}}})
    with pytest.raises(ConfigError, match="baseURL"):
        _from_file(path)


def test_from_file_bad_capabilities(tmp_path):
    path = write_config(tmp_path, {"backends": {"a": {"baseURL": "http://x", "capabilities": ["magic"]}}})
    with pytest.raises(ConfigError, match="unknown capabilities"):
        _from_file(path)


def test_from_file_bad_numbers(tmp_path):
    path = write_config(tmp_path, {"backends": {"a": {"baseURL": "http://x", "timeoutMs": -1}}})
    with pytest.raises(ConfigError, match="timeoutMs"):
        _from_file(path)


def test_from_file_invalid_json(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(ConfigError, match="not valid JSON"):
        _from_file(path)


def test_capability_selection(tmp_path):
    path = write_config(
        tmp_path,
        {
            "defaultBackend": "textual",
            "backends": {
                "textual": {"baseURL": "http://127.0.0.1:5001", "capabilities": ["text"]},
                "visual": {"baseURL": "http://127.0.0.1:8080", "capabilities": ["vision"]},
            },
        },
    )
    config = _from_file(path)
    assert config.get(None, "text").name == "textual"
    assert config.get("visual", "vision").name == "visual"
    with pytest.raises(ConfigError, match="does not declare capability"):
        config.get("visual", "text")


def test_capability_selection_errors(tmp_path):
    path = write_config(
        tmp_path,
        {
            "backends": {
                "textual": {"baseURL": "http://127.0.0.1:5001", "capabilities": ["text"]},
                "other": {"baseURL": "http://127.0.0.1:5002", "capabilities": ["text"]},
            },
        },
    )
    config = _from_file(path)
    with pytest.raises(ConfigError, match="unknown backend|not configured"):
        config.get("ghost", "text")
    with pytest.raises(ConfigError, match="no backend declares capability"):
        config.get(None, "vision")
    with pytest.raises(ConfigError, match="multiple backends"):
        config.get(None, "text")


def test_default_backend_missing_capability(tmp_path):
    path = write_config(
        tmp_path,
        {
            "defaultBackend": "textual",
            "backends": {
                "textual": {"baseURL": "http://127.0.0.1:5001", "capabilities": ["text"]},
                "visual": {"baseURL": "http://127.0.0.1:8080", "capabilities": ["vision"]},
            },
        },
    )
    config = _from_file(path)
    with pytest.raises(ConfigError, match="default backend"):
        config.get(None, "vision")


def test_env_backend(monkeypatch):
    monkeypatch.setenv(BASE_URL_ENV, "http://127.0.0.1:5001")
    config = _from_env()
    assert config.backends["env"].base_url == "http://127.0.0.1:5001"
    assert config.backends["env"].model == "local"
    assert config.get(None, "text").name == "env"


def test_env_backend_missing(monkeypatch):
    monkeypatch.delenv(BASE_URL_ENV, raising=False)
    with pytest.raises(ConfigError, match="not configured"):
        _from_env()


def test_config_source_hot_reload(tmp_path, monkeypatch):
    path = write_config(tmp_path, {"backends": {"a": {"baseURL": "http://127.0.0.1:5001"}}})
    monkeypatch.setenv("MULTHANDS_CONFIG", str(path))
    source = ConfigSource()
    first = source.get()
    assert first.backends["a"].base_url == "http://127.0.0.1:5001"

    # Same-size rewrite within one Windows timestamp tick: still picked up.
    path.write_text(
        json.dumps({"backends": {"a": {"baseURL": "http://127.0.0.1:6000"}}}),
        encoding="utf-8",
    )
    second = source.get()
    assert second.backends["a"].base_url == "http://127.0.0.1:6000"


def test_config_source_last_good_fallback(tmp_path, monkeypatch):
    path = write_config(tmp_path, {"backends": {"a": {"baseURL": "http://127.0.0.1:5001"}}})
    monkeypatch.setenv("MULTHANDS_CONFIG", str(path))
    source = ConfigSource()
    source.get()

    path.write_text("{broken json", encoding="utf-8")
    fallback = source.get()
    assert fallback.backends["a"].base_url == "http://127.0.0.1:5001"

    path.write_text(
        json.dumps({"backends": {"a": {"baseURL": "http://127.0.0.1:6000"}}}),
        encoding="utf-8",
    )
    recovered = source.get()
    assert recovered.backends["a"].base_url == "http://127.0.0.1:6000"