"""OpenAI-compatible Meterless Runtime provider and local credential store."""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import parse_qs, urlsplit, urlunsplit

from agents import config

PROVIDER_ID = "meterless"
PROVIDER_NAME = "Meterless Runtime"
DEFAULT_BASE_URL = "http://127.0.0.1:8088/v1"
APP_ID = "gen-ai-land-title-check"
STATE_DIR = config.ROOT / ".state"
SETTINGS_FILE = STATE_DIR / "provider-settings.json"
PROXY_TOKEN_FILE = STATE_DIR / "proxy-token"
INVALID_TOKENS = {"", "rt-local", "your-nightshift-runtime-token"}
DISPOSITIONS = {"auto", "fast", "deep", "cheap", "local", "fusion"}
DETECT_HOSTS = ("127.0.0.1", "localhost", "[::1]")
DETECT_PORTS = (8088, 8090, 8787, 11434)


def parse_connect_link(value: str) -> tuple[str, str] | None:
    """Return normalized origin URL and key from http(s)://host:port/connect#k=..."""
    try:
        parts = urlsplit(value.strip())
        if parts.scheme not in {"http", "https"} or not parts.hostname or parts.path.rstrip("/") != "/connect":
            return None
        if parts.username or parts.password:
            return None
        key = parse_qs(parts.fragment, keep_blank_values=True).get("k", [""])[0].strip()
        if not key or key.casefold() in INVALID_TOKENS:
            raise ValueError("Connect link must include a valid Runtime key in #k=")
        return normalize_base_url(urlunsplit((parts.scheme, parts.netloc, "", "", ""))), key
    except (ValueError, IndexError):
        return None


def normalize_base_url(value: str | None) -> str:
    """Normalize pasted host/endpoint variants to exactly <origin>/v1."""
    raw = (value or DEFAULT_BASE_URL).strip()
    if not raw:
        raw = DEFAULT_BASE_URL
    if "://" not in raw:
        raw = "http://" + raw
    parts = urlsplit(raw)
    if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username or parts.password:
        raise ValueError("Enter a valid HTTP(S) runtime URL")
    path = re.sub(r"/+", "/", parts.path or "").rstrip("/")
    for suffix in ("/v1/chat/completions", "/v1/models", "/healthz", "/v1"):
        if path.casefold().endswith(suffix):
            path = path[: -len(suffix)]
            break
    while path.casefold().endswith("/v1"):
        path = path[:-3].rstrip("/")
    origin = urlunsplit((parts.scheme, parts.netloc, "", "", ""))
    return origin + (path if path else "") + "/v1"


def _read_settings() -> dict[str, Any]:
    try:
        value = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_settings(value: dict[str, Any]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    temporary = SETTINGS_FILE.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2), encoding="utf-8")
    try:
        os.chmod(temporary, 0o600)
    except OSError:
        pass
    temporary.replace(SETTINGS_FILE)


def current_settings() -> dict[str, str]:
    settings = _read_settings()
    token = str(settings.get("meterless_runtime_token") or "").strip()
    if not token:
        try:
            token = PROXY_TOKEN_FILE.read_text(encoding="utf-8").strip()
        except OSError:
            token = ""
        if token and _valid_token(token):
            settings["meterless_runtime_token"] = token
            _write_settings(settings)
    if not token:
        token = config.METERLESS_RUNTIME_TOKEN
        if token and _valid_token(token):
            settings["meterless_runtime_token"] = token
            _write_settings(settings)
    base = str(settings.get("meterless_base_url") or config.METERLESS_BASE_URL or DEFAULT_BASE_URL)
    try:
        base = normalize_base_url(base)
    except ValueError:
        base = DEFAULT_BASE_URL
    model = str(settings.get("meterless_model") or config.METERLESS_MODEL)
    if not model.startswith("meterless/"):
        model = "meterless/auto"
    return {"base_url": base, "token": token, "model": model}


def save_settings(base_url: str, token: str | None = None, model: str | None = None) -> dict[str, str]:
    normalized = normalize_base_url(base_url)
    if token is None:
        current_settings()  # imports the runtime's proxy-token file when present
    current = _read_settings()
    if token is not None:
        token = token.strip()
        if token.casefold() in INVALID_TOKENS:
            raise ValueError("Paste the Runtime token; rt-local is only a placeholder")
        current["meterless_runtime_token"] = token
    if model is not None:
        if not model.startswith("meterless/"):
            raise ValueError("Meterless model ids must start with meterless/")
        current["meterless_model"] = model
    elif not str(current.get("meterless_model") or config.METERLESS_MODEL).startswith("meterless/"):
        current["meterless_model"] = "meterless/auto"
    current["meterless_base_url"] = normalized
    _write_settings(current)
    return {"base_url": normalized, "token": str(current.get("meterless_runtime_token") or ""),
            "model": str(current.get("meterless_model") or config.METERLESS_MODEL)}


def _valid_token(token: str) -> bool:
    return token.strip().casefold() not in INVALID_TOKENS


def _request(url: str, token: str, *, body: bytes | None = None, chat: bool = False,
             timeout: int = 10) -> tuple[int, Any]:
    headers = {
        "Authorization": f"Bearer {token}",
        "meterless-app": APP_ID,
        "Accept": "application/json",
    }
    if body is not None:
        headers["Content-Type"] = "application/json"
    if chat:
        headers["meterless-scope"] = "user"
    request = urllib.request.Request(url, data=body, headers=headers, method="POST" if body is not None else "GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = response.read()
            try:
                return response.status, json.loads(payload)
            except (ValueError, UnicodeDecodeError):
                return response.status, None
    except urllib.error.HTTPError as exc:
        # Preserve auth status as a distinct provider state; never expose URL/key/body.
        return exc.code, None
    except (urllib.error.URLError, TimeoutError, OSError):
        return 0, None


def list_models(base_url: str, token: str) -> tuple[str, list[dict[str, str]]]:
    if not _valid_token(token):
        return "offline", []
    status, payload = _request(normalize_base_url(base_url) + "/models", token, timeout=3)
    if status in (401, 403):
        return "unauthorized", []
    if status != 200 or not isinstance(payload, dict):
        return "offline", []
    data = payload.get("data")
    if not isinstance(data, list):
        return "offline", []
    found: list[dict[str, str]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        model_id = item.get("id")
        if isinstance(model_id, str) and model_id.startswith("meterless/"):
            disposition = model_disposition(model_id)
            found.append({"id": model_id, "disposition": disposition})
    return ("online", found) if found else ("offline", [])


def model_disposition(model_id: str) -> str:
    """Return a known routing disposition while retaining unknown meterless ids."""
    suffix = model_id.removeprefix("meterless/")
    if suffix in DISPOSITIONS:
        return suffix
    if "." in suffix:
        candidate = suffix.rsplit(".", 1)[1]
        if candidate in DISPOSITIONS:
            return candidate
    return "other"


def auto_detect(token: str) -> tuple[str, str, list[dict[str, str]]]:
    """Probe the documented loopback host/port matrix and save first auth/online hit."""
    for port in DETECT_PORTS:
        for host in DETECT_HOSTS:
            base = f"http://{host}:{port}/v1"
            status, models = list_models(base, token)
            if status in {"online", "unauthorized"}:
                selected = current_settings()["model"]
                if status == "online" and models and selected not in {item["id"] for item in models}:
                    selected = models[0]["id"]
                save_settings(base, token if _valid_token(token) else None, selected)
                return status, normalize_base_url(base), models
    return "offline", "", []


def chat_completion(base_url: str, token: str, model: str, messages: list[dict[str, Any]],
                    *, response_format: dict[str, str] | None = None,
                    temperature: float | None = None) -> dict[str, Any]:
    if not _valid_token(token):
        raise PermissionError("Meterless Runtime token is required")
    if not model.startswith("meterless/"):
        raise ValueError("Choose a model id returned by Meterless Runtime")
    request_body: dict[str, Any] = {"model": model, "messages": messages}
    if response_format is not None:
        request_body["response_format"] = response_format
    if temperature is not None:
        request_body["temperature"] = temperature
    body = json.dumps(request_body).encode("utf-8")
    status, payload = _request(
        normalize_base_url(base_url) + "/chat/completions", token, body=body, chat=True, timeout=180,
    )
    if status in (401, 403):
        raise PermissionError("Meterless Runtime rejected the token")
    if status != 200 or not isinstance(payload, dict):
        raise RuntimeError(f"Meterless Runtime request failed (HTTP {status or 'unreachable'})")
    return payload

