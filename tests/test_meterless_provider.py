import json
import shutil
import uuid
from unittest.mock import patch

import pytest

from agents import api, meterless_provider as provider


def _state_store(request, monkeypatch):
    directory = provider.config.ROOT / ".state" / f"provider-test-{uuid.uuid4().hex}"
    directory.mkdir(parents=True)
    request.addfinalizer(lambda: shutil.rmtree(directory, ignore_errors=True))
    monkeypatch.setattr(provider, "STATE_DIR", directory)
    monkeypatch.setattr(provider, "SETTINGS_FILE", directory / "provider-settings.json")
    monkeypatch.setattr(provider, "PROXY_TOKEN_FILE", directory / "proxy-token")
    return directory


@pytest.mark.parametrize("pasted", [
    "127.0.0.1:8088",
    "http://127.0.0.1:8088/v1",
    "http://127.0.0.1:8088/v1/chat/completions",
    "http://127.0.0.1:8088/v1/models",
    "http://127.0.0.1:8088/healthz",
    "http://127.0.0.1:8088/v1/v1/models",
])
def test_normalize_runtime_endpoint_to_single_v1(pasted):
    normalized = provider.normalize_base_url(pasted)
    assert normalized == "http://127.0.0.1:8088/v1"
    assert "/v1/v1" not in normalized


def test_connect_link_extracts_key_without_retaining_connect_path():
    assert provider.parse_connect_link("http://localhost:8088/connect#k=runtime-key") == (
        "http://localhost:8088/v1", "runtime-key"
    )


def test_placeholder_token_is_rejected(request, monkeypatch):
    _state_store(request, monkeypatch)
    with pytest.raises(ValueError, match="rt-local"):
        provider.save_settings("localhost:8088", "rt-local")


def test_wrong_token_is_unauthorized_not_offline():
    with patch.object(provider, "_request", return_value=(401, None)) as request:
        status, models = provider.list_models("localhost:8088/v1/models", "wrong-token")
    assert status == "unauthorized"
    assert models == []
    assert request.call_args.args[0] == "http://localhost:8088/v1/models"


def test_models_keep_unknown_meterless_routing_ids():
    payload = {"data": [{"id": "meterless/auto"}, {"id": "meterless/land.deep"},
                        {"id": "meterless/new-mode"}, {"id": "gpt-example"}]}
    with patch.object(provider, "_request", return_value=(200, payload)):
        status, models = provider.list_models("http://localhost:8088/v1", "valid")
    assert status == "online"
    assert [item["id"] for item in models] == [
        "meterless/auto", "meterless/land.deep", "meterless/new-mode"
    ]
    assert models[1]["disposition"] == "deep"
    assert models[2]["disposition"] == "other"


def test_selected_routing_mode_is_persisted(request, monkeypatch):
    _state_store(request, monkeypatch)
    saved = provider.save_settings("localhost:8088", "valid", "meterless/land.deep")
    assert saved["model"] == "meterless/land.deep"
    assert provider.current_settings()["model"] == "meterless/land.deep"


def test_chat_uses_bearer_headers_long_timeout_and_plain_string_content():
    response_payload = {"choices": [{"message": {"content": "ready"}}]}

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self):
            return json.dumps(response_payload).encode()

    messages = [{"role": "user", "content": "Say ready"}]
    with patch("agents.meterless_provider.urllib.request.urlopen", return_value=Response()) as open_url:
        result = provider.chat_completion("localhost:8088/v1", "secret", "meterless/auto", messages)
    http_request = open_url.call_args.args[0]
    sent = json.loads(http_request.data)
    assert sent["messages"] == messages
    assert isinstance(sent["messages"][0]["content"], str)
    assert http_request.get_header("Authorization") == "Bearer secret"
    assert http_request.get_header("Meterless-app") == provider.APP_ID
    assert http_request.get_header("Meterless-scope") == "user"
    assert open_url.call_args.kwargs["timeout"] == 180
    assert result["choices"][0]["message"]["content"] == "ready"


def test_auto_detect_saves_first_online_or_unauthorized_hit(request, monkeypatch):
    directory = _state_store(request, monkeypatch)
    with patch.object(provider, "list_models", side_effect=[("offline", []), ("unauthorized", [])]) as probe:
        status, base_url, models = provider.auto_detect("wrong-token")
    assert status == "unauthorized"
    assert base_url == "http://localhost:8088/v1"
    assert models == []
    assert probe.call_count == 2
    saved = json.loads((directory / "provider-settings.json").read_text())
    assert saved["meterless_runtime_token"] == "wrong-token"


def test_proxy_token_is_imported_and_stored_under_contract_key(request, monkeypatch):
    directory = _state_store(request, monkeypatch)
    (directory / "proxy-token").write_text("runtime-key")
    assert provider.current_settings()["token"] == "runtime-key"
    stored = json.loads((directory / "provider-settings.json").read_text())
    assert stored["meterless_runtime_token"] == "runtime-key"


def test_api_reports_wrong_token_as_unauthorized(monkeypatch):
    monkeypatch.setattr(api, "current_settings", lambda: {"base_url": provider.DEFAULT_BASE_URL, "token": "wrong", "model": "meterless/auto"})
    monkeypatch.setattr(api, "list_models", lambda _base, _token: ("unauthorized", []))
    result = api.meterless_provider_status()
    assert result["status"] == "unauthorized"
    assert result["needs_token"] is True


def test_api_plain_text_chat_preserves_user_message_as_string(monkeypatch):
    monkeypatch.setattr(api, "current_settings", lambda: {"base_url": provider.DEFAULT_BASE_URL, "token": "valid"})
    captured = {}

    def fake_chat(_base, _token, model, messages):
        captured["model"] = model
        captured["messages"] = messages
        return {"choices": [{"message": {"content": "ready"}}]}

    monkeypatch.setattr(api, "chat_completion", fake_chat)
    result = api.meterless_chat(api.MeterlessChatInput(model="meterless/auto", message="Say ready"))
    assert captured["model"] == "meterless/auto"
    assert captured["messages"] == [{"role": "user", "content": "Say ready"}]
    assert isinstance(captured["messages"][0]["content"], str)
    assert result == {"content": "ready"}
