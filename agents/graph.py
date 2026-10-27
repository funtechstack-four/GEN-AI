"""LangGraph orchestration for evidence-led land title checks."""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from agents import config
from agents.classifier import analyze
from agents.critic import critic_claim, quote_for
from agents.sources import query_cancelled_serial, query_judgments, query_notices, query_registry, serial_notice_quote
from agents.trace import record
from data import normalizer

REMAINING_CHECKS = [
    "Obtain an official land registry search",
    "Match the seller's identification to the registered owner",
    "Visit the property and verify its boundaries with a beacon survey",
    "Ask an advocate to review the register and transaction documents",
]


class AgentState(TypedDict, total=False):
    intake: dict[str, str]
    run_id: str
    parcel: Any
    candidates: list[dict[str, Any]]
    claims: list[dict[str, Any]]
    registry: list[dict[str, Any]]
    memory: dict[str, Any]
    source_warnings: list[str]
    dossier: dict[str, Any]
    early_stop: bool


def _source_id(row: dict[str, Any], source_type: str) -> str:
    if source_type == "gazette":
        return str(row.get("notice_id") or f"{row.get('issue_date', '')}:{row.get('notice_no', '')}")
    return str(row.get("judgment_id") or row.get("case_no") or "unknown")


def intake_normalizer(state: AgentState) -> dict[str, Any]:
    pid = normalizer.normalise(state["intake"]["parcel_input"])
    return {"parcel": pid, "claims": [], "candidates": [], "early_stop": False}


def serial_guard(state: AgentState) -> dict[str, Any]:
    intake, run_id = state["intake"], state["run_id"]
    serial = intake.get("title_serial", "").strip()
    row = query_cancelled_serial(serial) if serial else None
    if not row:
        return {"early_stop": False}
    date_text = str(row.get("issue_date") or "2024-09-27")[:10]
    src = str(row.get("gazette_notice_no") or "12436")
    claim = {
        "claim_id": "c1", "kind": "serial_cancelled", "parcel_id": state["intake"]["parcel_input"],
        "quote": serial_notice_quote(f"{date_text}:{src}") or str(row.get("quote") or f"Title serial {serial} is listed in Gazette Notice {src}"),
        "source_type": "gazette", "source_id": f"{date_text}:{src}",
        "status": "confirmed", "reject_reason": None,
    }
    record(run_id, "verdict", verdict="STOP", reason="cancelled title serial", agent="serial_guard")
    return {"early_stop": True, "claims": [claim]}


def investigate(state: AgentState) -> dict[str, Any]:
    run_id, intake, pid = state["run_id"], state["intake"], state.get("parcel")
    if pid is None:
        return {"candidates": [], "registry": []}
    record(run_id, "tool_call", tool="zetaris", operation="read-only parcel investigation", sample=config.SAMPLE_MODE)
    variants = normalizer.variants(pid)
    notices = query_notices(pid.label, variants)
    judgments = query_judgments(pid.label, variants)
    registry = query_registry(pid.label, pid.key)
    warnings = []
    if not config.SAMPLE_MODE and not config.ZETARIS_JUDGMENTS_TABLE:
        warnings.append("Court judgments are not registered in Zetaris; this dossier uses Gazette sources only")
    if not config.SAMPLE_MODE and not config.ZETARIS_REGISTRY_TABLE:
        warnings.append("No registry table is configured in Zetaris; an official land search remains necessary")
    candidates = [{"source_type": "gazette", "row": r} for r in notices]
    candidates += [{"source_type": "judgment", "row": r} for r in judgments]
    record(run_id, "delegate", agent="court_investigator", candidate_count=len(judgments))
    return {"candidates": candidates, "registry": registry, "source_warnings": warnings}


def evidence_critic(state: AgentState) -> dict[str, Any]:
    run_id, pid = state["run_id"], state.get("parcel")
    if pid is None:
        return {"claims": []}
    out: list[dict[str, Any]] = []
    for candidate in state.get("candidates", []):
        row, source_type = dict(candidate["row"]), candidate["source_type"]
        text = str(row.get("raw_text") or row.get("excerpt") or "")
        analysis = analyze(row)
        kind = analysis["kind"]
        if analysis["kind_source"] == "nemotron":
            record(run_id, "nemotron_proposal", source_id=_source_id(row, source_type), kind=kind,
                   party_count=len(analysis["parties"]))
        if kind not in {"lost_title", "succession", "dispute", "court_order", "acquisition", "transfer"}:
            continue
        # Nemotron party names are proposals only. Meterless applies an additional
        # exact-source-text check before any name is persisted to memory.
        if analysis["parties"] and not row.get("parties"):
            row["parties"] = analysis["parties"]
            candidate["row"] = row
        quote = quote_for(pid.label, text)
        claim = {
            "claim_id": f"c{len(out) + 1}", "kind": kind, "parcel_id": pid.label, "quote": quote,
            "source_type": source_type, "source_id": _source_id(row, source_type),
            "classification_source": analysis["kind_source"],
            "status": "pending", "reject_reason": None,
        }
        ok, reason = critic_claim(pid.label, row, claim)
        claim["status"] = "confirmed" if ok else "rejected"
        claim["reject_reason"] = None if ok else reason
        out.append(claim)
        if ok:
            record(run_id, "critic_accept", claim_id=claim["claim_id"], source_id=claim["source_id"])
        else:
            record(run_id, "critic_reject", claim_id=claim["claim_id"], reason=reason)
    return {"claims": out}


def meterless_context(state: AgentState) -> dict[str, Any]:
    """Update persistent World Model and H-MEM from critic-confirmed evidence only."""
    confirmed = [c for c in state.get("claims", []) if c["status"] == "confirmed"]
    if not confirmed:
        return {"memory": {"status": "no_confirmed_evidence", "source_ids": []}}
    try:
        from agents.meterless import record_evidence
        by_source = {_source_id(x["row"], "gazette"): x["row"] for x in state.get("candidates", []) if x["source_type"] == "gazette"}
        memory_claims = []
        for claim in confirmed:
            row = by_source.get(claim["source_id"], {})
            text = " ".join(str(row.get("raw_text") or "").split()).casefold()
            names = row.get("parties") or []
            if isinstance(names, str):
                try:
                    import json
                    names = json.loads(names)
                except ValueError:
                    names = [names]
            validated = [
                str(name).strip()[:200] for name in names[:10]
                if isinstance(name, str) and len(name.strip()) >= 3 and " ".join(name.split()).casefold() in text
            ] if isinstance(names, list) else []
            memory_claims.append({**claim, "parties": validated})
        result = record_evidence(state["run_id"], state["parcel"].label, memory_claims)
        record(state["run_id"], "meterless_context", world_model=result.get("world", {}), hmem=result.get("memory", {}))
        memory = dict(result.get("memory", {}))
        current = {claim["source_id"] for claim in confirmed}
        memory["prior_source_ids"] = [
            source_id for source_id in memory.get("source_ids", []) if source_id not in current
        ]
        memory["world_source_count"] = result.get("world", {}).get("source_count", 0)
        memory["party_patterns"] = result.get("memory", {}).get("party_patterns", [])
        return {"memory": memory}
    except Exception as exc:
        record(state["run_id"], "meterless_unavailable", reason=type(exc).__name__)
        return {"memory": {"status": "unavailable", "source_ids": []}}


def assess_and_write(state: AgentState) -> dict[str, Any]:
    intake, run_id = state["intake"], state["run_id"]
    claims = state.get("claims", [])
    if state.get("early_stop"):
        confirmed, unverified = claims, []
        verdict = "STOP"
    else:
        confirmed = [c for c in claims if c["status"] == "confirmed"]
        unverified = [c for c in claims if c["status"] != "confirmed"]
        sale = date.fromisoformat(intake["sale_date"])
        recent = any(
            c["kind"] == "lost_title"
            and 0 <= (sale - date.fromisoformat(c["source_id"][:10])).days <= 365
            for c in confirmed if c["source_type"] == "gazette"
        )
        court_stop = any(c["kind"] == "court_order" for c in confirmed)
        verdict = "STOP" if recent or court_stop else "HIGH RISK" if confirmed else "VERIFY FIRST"

    windows = []
    for claim in confirmed:
        if claim["source_type"] != "gazette":
            continue
        candidate = next((x["row"] for x in state.get("candidates", []) if _source_id(x["row"], "gazette") == claim["source_id"]), {})
        days = candidate.get("objection_days")
        try:
            days = int(days)
            published = date.fromisoformat(claim["source_id"][:10])
            closes = published + timedelta(days=days)
            if closes.weekday() == 6:  # Gazette guidance moves Sunday deadlines to Monday.
                closes += timedelta(days=1)
            sale = date.fromisoformat(intake["sale_date"])
            windows.append({"notice_id": claim["source_id"], "closes_on": closes.isoformat(), "open": published <= sale <= closes})
        except (TypeError, ValueError):
            continue

    advocate = []
    if len([c for c in confirmed if c["kind"] == "lost_title"]) > 1:
        advocate.append("Multiple lost-title notices appear in the public record; have an advocate review the sequence")
    if any(c["kind"] in {"succession", "dispute", "court_order"} for c in confirmed):
        advocate.append("Have an advocate confirm the status and legal effect of the court or succession record")
    if any(str(r.get("synthetic", "")).lower() == "true" for r in state.get("registry", [])):
        advocate.append("The registry row is synthetic demo data and is not an official register search")
    advocate.extend(state.get("source_warnings", []))
    memory = state.get("memory", {})
    if memory.get("world_source_count"):
        advocate.append(f"Meterless World Model linked {memory['world_source_count']} confirmed source records to this parcel")
    prior_refs = memory.get("prior_source_ids", [])
    if prior_refs:
        advocate.append(
            "Meterless H-MEM recalled earlier source references " + ", ".join(prior_refs[:5])
            + "; recheck each against its original record"
        )
    for pattern in memory.get("party_patterns", []):
        refs = ", ".join(pattern.get("source_ids", [])[:5])
        advocate.append(
            f"Meterless H-MEM found one named party recurring across {pattern.get('notice_count', 0)} lost-title notices"
            + (f" ({refs}); review the original records" if refs else "; review the original records")
        )
    dossier = {
        "run_id": run_id,
        "parcel_input": intake["parcel_input"],
        "verdict": verdict,
        "timeline": sorted(confirmed, key=lambda c: (c["source_id"][:10], c["source_id"])),
        "unverified": unverified,
        "objection_windows": windows,
        "remaining_checks": REMAINING_CHECKS,
        "advocate_review": advocate,
    }
    record(run_id, "verdict", verdict=verdict, confirmed=len(confirmed), unverified=len(unverified))
    return {"dossier": dossier}


def _route_after_serial(state: AgentState) -> str:
    return "assess" if state.get("early_stop") else "investigate"


builder = StateGraph(AgentState)
builder.add_node("intake_normalizer", intake_normalizer)
builder.add_node("serial_guard", serial_guard)
builder.add_node("investigate", investigate)
builder.add_node("evidence_critic", evidence_critic)
builder.add_node("meterless_context", meterless_context)
builder.add_node("assess", assess_and_write)
builder.add_edge(START, "intake_normalizer")
builder.add_edge("intake_normalizer", "serial_guard")
builder.add_conditional_edges("serial_guard", _route_after_serial, {"assess": "assess", "investigate": "investigate"})
builder.add_edge("investigate", "evidence_critic")
builder.add_edge("evidence_critic", "meterless_context")
builder.add_edge("meterless_context", "assess")
builder.add_edge("assess", END)
graph = builder.compile()


def run_dossier(intake: dict[str, str]) -> dict[str, Any]:
    run_id = uuid.uuid4().hex
    result = graph.invoke({"intake": intake, "run_id": run_id})
    return result["dossier"]
