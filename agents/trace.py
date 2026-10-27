"""Append-only, per-run workflow trace used by the UI and eval harness."""
from __future__ import annotations

import json
import pathlib
from datetime import datetime, timezone
from typing import Any

from agents.config import ROOT


def record(run_id: str, event: str, **fields: Any) -> None:
    path = ROOT / "logs" / f"{run_id}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    item = {"at": datetime.now(timezone.utc).isoformat(), "event": event, **fields}
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(item, ensure_ascii=False, default=str) + "\n")
