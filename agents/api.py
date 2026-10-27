"""FastAPI entry point for the Land Title Due-Diligence agent workflow."""
from __future__ import annotations

from datetime import date
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from agents.contracts import Dossier, IntakeRequest
from agents.graph import run_dossier
from agents.meterless_provider import (
    PROVIDER_ID, PROVIDER_NAME, auto_detect, chat_completion, current_settings,
    list_models, normalize_base_url, parse_connect_link, save_settings,
)
from agents.sources import SourceError

app = FastAPI(title="Land Title Due-Diligence Agents", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3100", "http://127.0.0.1:3100"],
    allow_methods=["GET", "POST", "PUT"],
    allow_headers=["content-type"],
)


class MeterlessSettingsInput(BaseModel):
    base_url: str = "http://127.0.0.1:8088/v1"
    token: str | None = None
    model: str | None = None


class MeterlessDetectInput(BaseModel):
    token: str | None = None


class MeterlessChatInput(BaseModel):
    model: str
    message: str


def _meterless_provider_payload(base_url: str, token: str) -> dict:
    status, models = list_models(base_url, token)
    selected = current_settings()["model"]
    available = {item["id"] for item in models}
    if status == "online" and models and selected not in available:
        selected = save_settings(base_url, None, models[0]["id"])["model"]
    return {
        "id": PROVIDER_ID, "name": PROVIDER_NAME, "base_url": normalize_base_url(base_url),
        "status": status, "models": models, "token_configured": bool(token),
        "needs_token": status == "unauthorized" or not token,
        "selected_model": selected,
    }


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/providers/meterless")
def meterless_provider_status() -> dict:
    settings = current_settings()
    return _meterless_provider_payload(settings["base_url"], settings["token"])


@app.put("/providers/meterless")
def configure_meterless_provider(request: MeterlessSettingsInput) -> dict:
    pasted = request.base_url.strip()
    try:
        connect = parse_connect_link(pasted)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if connect:
        base_url, token = connect
    else:
        candidate = pasted if "://" in pasted else "http://" + pasted
        if urlsplit(candidate).path.rstrip("/").casefold() == "/connect":
            raise HTTPException(status_code=422, detail="Connect link must include a valid key in #k=")
        base_url = pasted
        token = request.token
    try:
        settings = save_settings(base_url, token, request.model)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _meterless_provider_payload(settings["base_url"], settings["token"])


@app.post("/providers/meterless/detect")
def detect_meterless_provider(request: MeterlessDetectInput) -> dict:
    settings = current_settings()
    token = (request.token or settings["token"]).strip()
    if token.casefold() in {"", "rt-local", "your-nightshift-runtime-token"}:
        return {"id": PROVIDER_ID, "name": PROVIDER_NAME, "base_url": "", "status": "offline",
                "models": [], "token_configured": False, "needs_token": True}
    status, base_url, models = auto_detect(token)
    return {"id": PROVIDER_ID, "name": PROVIDER_NAME, "base_url": base_url, "status": status,
            "models": models, "token_configured": True, "needs_token": status == "unauthorized",
            "selected_model": current_settings()["model"]}


@app.post("/providers/meterless/chat")
def meterless_chat(request: MeterlessChatInput) -> dict[str, str]:
    settings = current_settings()
    try:
        response = chat_completion(
            settings["base_url"], settings["token"], request.model,
            [{"role": "user", "content": request.message}],
        )
    except PermissionError as exc:
        raise HTTPException(status_code=401, detail="Meterless Runtime token was rejected") from exc
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    try:
        content = response["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise HTTPException(status_code=502, detail="Meterless Runtime returned an invalid chat response") from exc
    if not isinstance(content, str):
        raise HTTPException(status_code=502, detail="Meterless Runtime did not return a plain text response")
    return {"content": content}


@app.post("/dossier", response_model=Dossier)
def dossier(request: IntakeRequest) -> Dossier:
    try:
        date.fromisoformat(request.sale_date)
        result = run_dossier(request.model_dump())
        return Dossier.model_validate(result)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="sale_date must be a valid ISO date") from exc
    except SourceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
