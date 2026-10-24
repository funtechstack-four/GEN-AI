"""Shared helpers for the data scripts: paths, logging (stdout + logs/), polite fetching."""
from __future__ import annotations

import csv
import logging
import pathlib
import sys
import time

from scrapling.fetchers import Fetcher

ROOT = pathlib.Path(__file__).resolve().parents[2]
EXTRACTS = ROOT / "data" / "extracts"
RAW_PDF = ROOT / "data" / "raw" / "gazette"
LOGS = ROOT / "logs"

ISSUES_CSV = EXTRACTS / "gazette_issues.csv"
NOTICES_PARQUET = EXTRACTS / "gazette_notices.parquet"


def pdf_name(issue_date: str, gazette_no: str) -> str:
    """Local file name for an issue."""
    return f"ke-government-gazette-dated-{issue_date}-no-{gazette_no}.pdf"


def read_issues() -> dict[str, dict]:
    """gazette_issues.csv rows keyed by local PDF file name."""
    with ISSUES_CSV.open(encoding="utf-8") as f:
        return {pdf_name(r["issue_date"], r["gazette_no"]): r for r in csv.DictReader(f)}


def get_logger(name: str) -> logging.Logger:
    LOGS.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    log = logging.getLogger(name)
    if not log.handlers:
        log.setLevel(logging.INFO)
        for h in (logging.StreamHandler(sys.stdout), logging.FileHandler(LOGS / "data-scripts.log", encoding="utf-8")):
            h.setFormatter(fmt)
            log.addHandler(h)
    return log


def fetch_bytes(url: str, log: logging.Logger, tries: int = 3, timeout: int = 120) -> bytes | None:
    """GET with Scrapling, backing off on errors and 5xx. Returns None on 403/404."""
    for attempt in range(1, tries + 1):
        try:
            page = Fetcher.get(url, timeout=timeout)
            if page.status in (403, 404):
                log.warning("HTTP %s for %s", page.status, url)
                return None
            if page.status == 200:
                return page.body
            log.warning("HTTP %s for %s (attempt %d/%d)", page.status, url, attempt, tries)
        except Exception as exc:  # network errors differ by backend
            log.warning("%s for %s (attempt %d/%d)", type(exc).__name__, url, attempt, tries)
        time.sleep(2 * attempt)
    log.error("giving up on %s after %d attempts", url, tries)
    return None
