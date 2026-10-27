"""The frozen API contracts mirrored by web/lib/contracts.ts."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Verdict = Literal["STOP", "HIGH RISK", "VERIFY FIRST"]
ClaimKind = Literal[
    "serial_cancelled", "lost_title", "succession", "dispute", "court_order",
    "acquisition", "transfer",
]
SourceType = Literal["gazette", "judgment", "serial_list", "registry"]


class IntakeRequest(BaseModel):
    parcel_input: str = Field(min_length=1, max_length=500)
    title_serial: str = Field(default="", max_length=100)
    seller_name: str = Field(default="", max_length=300)
    sale_date: str = Field(min_length=10, max_length=10)


class Claim(BaseModel):
    claim_id: str
    kind: ClaimKind
    parcel_id: str
    quote: str
    source_type: SourceType
    source_id: str
    status: Literal["pending", "confirmed", "rejected", "unverified"]
    reject_reason: str | None = None


class ObjectionWindow(BaseModel):
    notice_id: str
    closes_on: str
    open: bool


class Dossier(BaseModel):
    run_id: str
    parcel_input: str
    verdict: Verdict
    timeline: list[Claim]
    unverified: list[Claim]
    objection_windows: list[ObjectionWindow]
    remaining_checks: list[str]
    advocate_review: list[str]
