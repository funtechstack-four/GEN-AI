"""HTTP client for the local Meterless reference-engine bridge."""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from agents import config


def record_evidence(run_id: str, parcel: str, claims: list[dict[str, Any]]) -> dict[str, Any]:
    body = json.dumps({"run_id": run_id, "parcel": parcel, "claims": claims}).encode()
    req = urllib.request.Request(
        f"{config.METERLESS_BRIDGE_URL}/context",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            payload = json.loads(response.read())
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError("Meterless bridge request failed") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("Meterless bridge returned an invalid response")
    return payload
