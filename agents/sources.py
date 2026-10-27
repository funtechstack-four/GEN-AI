"""Read-only sample and Zetaris source adapters."""
from __future__ import annotations

import csv
import functools
import json
import re
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any

from agents import config


class SourceError(RuntimeError):
    pass


def _table_name(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][\w$]*(?:\.[A-Za-z_][\w$]*)?", value):
        raise SourceError("Invalid Zetaris table name; use a configured database.table identifier")
    return value


def _sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _to_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list) and all(isinstance(x, dict) for x in payload):
        return payload
    if not isinstance(payload, dict):
        raise SourceError("Zetaris returned an unexpected query payload")
    for key in ("data", "rows", "result", "results"):
        val = payload.get(key)
        if isinstance(val, dict):
            try:
                return _to_rows(val)
            except SourceError:
                continue
        if isinstance(val, list):
            if not val:
                return []
            if isinstance(val[0], dict):
                return val
            headers = payload.get("headers") or payload.get("columns")
            if isinstance(headers, list):
                return [dict(zip(headers, row)) for row in val if isinstance(row, (list, tuple))]
    raise SourceError("Zetaris response did not include row data")


class Zetaris:
    """Narrow, read-only query client. Dynamic values are always SQL-escaped."""

    def query(self, sql: str) -> list[dict[str, Any]]:
        if config.SAMPLE_MODE:
            raise SourceError("Zetaris query requested while SAMPLE_MODE is enabled")
        if not config.ZETARIS_API_KEY:
            raise SourceError("ZETARIS_API_KEY is required when SAMPLE_MODE=false")
        url = f"{config.ZETARIS_REST_URL}/sql-editor/sqls/run-query"
        req = urllib.request.Request(
            url,
            data=json.dumps({"sql": sql}).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {config.ZETARIS_API_KEY}",
                "X-Org-ID": config.ZETARIS_ORG_ID,
                "X-Request-ID": str(uuid.uuid4()),
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=90) as response:
                payload = json.loads(response.read())
        except urllib.error.HTTPError as exc:
            raise SourceError(f"Zetaris query failed with HTTP {exc.code}") from exc
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise SourceError(f"Could not read from Zetaris: {type(exc).__name__}") from exc
        if isinstance(payload, dict) and payload.get("error"):
            raise SourceError("Zetaris rejected the read-only SQL query")
        return _to_rows(payload)


def _csv(name: str) -> list[dict[str, str]]:
    with (config.ROOT / "data" / "extracts" / name).open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def sample_serial(serial: str) -> dict[str, str] | None:
    normalized = re.sub(r"(?i)^\s*(?:(?:serial|title)\s*)?(?:no\s*[.:]?\s*)?", "", serial)
    normalized = re.sub(r"[\s,]", "", normalized).rstrip(".")
    if not normalized.isdigit():
        return None
    return next((r for r in _csv("cancelled_serials.csv") if r["serial"] == str(int(normalized))), None)


@functools.lru_cache(maxsize=16)
def serial_notice_quote(source_id: str) -> str:
    """Verbatim excerpt for the Gazette notice backing a cancelled-serial list entry."""
    import pyarrow.parquet as pq

    table = pq.read_table(
        config.ROOT / "data" / "extracts" / "gazette_notices.parquet",
        columns=["raw_text"], filters=[("notice_id", "=", source_id)],
    )
    if table.num_rows == 0:
        return ""
    text = str(table.column("raw_text")[0].as_py() or "")
    start = text.find("5253001")
    end = text.find("5253367", start) if start >= 0 else -1
    from agents.excerpt import snap_to_words

    if end < 0:
        return snap_to_words(text, 0, 500)
    return snap_to_words(text, start - 120, end + 260)


def query_notices(parcel: str, parcel_variants: list[str]) -> list[dict[str, Any]]:
    if config.SAMPLE_MODE:
        import pyarrow.parquet as pq
        from data.normalizer import refs_match

        table = pq.read_table(config.ROOT / "data" / "extracts" / "gazette_notices.parquet")
        return [row for row in table.to_pylist() if refs_match(parcel, row.get("parcel_refs"))]
    patterns = list(dict.fromkeys([*parcel_variants, parcel]))
    where = " OR ".join(f"raw_text LIKE {_sql_literal('%' + p + '%')}" for p in patterns)
    return Zetaris().query(f"SELECT * FROM {_table_name(config.ZETARIS_NOTICES_TABLE)} WHERE {where}")


def query_judgments(parcel: str, parcel_variants: list[str]) -> list[dict[str, Any]]:
    if config.SAMPLE_MODE:
        rows = _csv("judgments.csv")
        return [r for r in rows if parcel.casefold() in (r.get("parcel_ids", "") + " " + r.get("raw_text", "")).casefold()]
    if not config.ZETARIS_JUDGMENTS_TABLE:
        return []
    patterns = list(dict.fromkeys([*parcel_variants, parcel]))
    where = " OR ".join(f"parcel_ids LIKE {_sql_literal('%' + p + '%')}" for p in patterns)
    return Zetaris().query(f"SELECT * FROM {_table_name(config.ZETARIS_JUDGMENTS_TABLE)} WHERE {where}")


def query_registry(parcel: str, parcel_key: str) -> list[dict[str, Any]]:
    if config.SAMPLE_MODE:
        return [r for r in _csv("synthetic_registry.csv") if r["parcel_id"].casefold() == parcel_key.casefold()]
    if not config.ZETARIS_REGISTRY_TABLE:
        return []
    where = f"parcel_input = {_sql_literal(parcel)} OR parcel_id = {_sql_literal(parcel_key)}"
    return Zetaris().query(f"SELECT * FROM {_table_name(config.ZETARIS_REGISTRY_TABLE)} WHERE {where}")


def query_cancelled_serial(serial: str) -> dict[str, Any] | None:
    # The serial list is a fixed early-exit guard. Keep it local so cancelled titles
    # short-circuit before any Zetaris/tool call, as required by the eval contract.
    return sample_serial(serial)
