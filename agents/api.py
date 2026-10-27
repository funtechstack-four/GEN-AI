"""FastAPI entry point for the Land Title Due-Diligence agent workflow."""
from __future__ import annotations

from datetime import date

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from agents.contracts import Dossier, IntakeRequest
from agents.graph import run_dossier
from agents.sources import SourceError

app = FastAPI(title="Land Title Due-Diligence Agents", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3100", "http://127.0.0.1:3100"],
    allow_methods=["GET", "POST"],
    allow_headers=["content-type"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


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
