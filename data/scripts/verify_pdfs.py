"""Check every downloaded Gazette PDF is the issue it claims to be.

For each file: it opens, has a text layer, and its page-1 masthead ("Vol. CXXVI-No. 147",
"NAIROBI, 27th September, 2024") matches the issue number and date in gazette_issues.csv.
Writes data/extracts/gazette_pdf_check.csv and prints a summary.

    python data/scripts/verify_pdfs.py
"""
from __future__ import annotations

import csv
import re
from datetime import datetime

import pymupdf

from common import EXTRACTS, RAW_PDF, get_logger, pdf_name, read_issues

# Matched against page 1 with all whitespace removed, because scanned issues OCR as
# "V ol . CX X V - No. 172" and "NAIROBI , 28th July". "No. 245 A" is issue 245A.
# OCR misreads seen: "EXXV" for "CXXV", a stray "I." after the number.
VOL_RE = re.compile(r"VOL\.?[CXLVIE]+\W{0,3}NO\.?(\d+)(?:\W?([A-D])(?![A-Z]))?")
DATE_RE = re.compile(r"NAIROBI,?(\d{1,2})(?:ST|ND|RD|TH)?([A-Z]+),?(\d{4})")
OUT = EXTRACTS / "gazette_pdf_check.csv"

log = get_logger("verify_pdfs")


def read_masthead(page_text: str) -> tuple[str | None, str | None]:
    """(issue number, ISO date) printed on page 1, or None for each part not found."""
    head = re.sub(r"\s+", "", page_text[:2000]).upper()
    vol, date = VOL_RE.search(head), DATE_RE.search(head)
    no = (vol.group(1) + (vol.group(2) or "").lower()) if vol else None
    iso = None
    if date:
        try:
            iso = datetime.strptime(" ".join(date.groups()), "%d %B %Y").date().isoformat()
        except ValueError:
            pass
    return no, iso


def masthead(path) -> tuple[int, int, str | None, str | None]:
    doc = pymupdf.open(path)
    text = "".join(p.get_text() for p in doc)
    no, iso = read_masthead(doc[0].get_text()) if doc.page_count else (None, None)
    return doc.page_count, len(text), no, iso


def main() -> None:
    issues = read_issues()
    results = []
    for name, row in sorted(issues.items()):
        path = RAW_PDF / row["year"] / pdf_name(row["issue_date"], row["gazette_no"])
        if not path.exists():
            results.append({**row, "status": "missing"})
            continue
        try:
            pages, chars, no, date = masthead(path)
        except Exception as exc:
            results.append({**row, "status": f"unreadable: {type(exc).__name__}"})
            continue
        problems = []
        if chars < 500:
            problems.append("no text layer")
        if no is None:
            problems.append("masthead number not found")
        elif no.lower() != row["gazette_no"].lower():
            problems.append(f"masthead says No. {no}")
        if date is None:
            problems.append("masthead date not found")
        elif date != row["issue_date"]:
            # The printed date is authoritative; extract_notices.py uses it. Flag, don't fail.
            problems.append(f"catalogue date differs, printed {date}")
        results.append({**row, "pages": pages, "chars": chars, "masthead_no": no, "masthead_date": date,
                        "status": "ok" if not problems else "; ".join(problems)})

    with OUT.open("w", newline="", encoding="utf-8") as f:
        fields = ["year", "issue_date", "gazette_no", "pdf_url", "pages", "chars", "masthead_no", "masthead_date", "status"]
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(results)

    present = [r for r in results if r["status"] != "missing"]
    ok = sum(r["status"] == "ok" for r in present)
    log.info("%d issues listed, %d on disk, %d verified ok, %d with problems", len(results), len(present), ok, len(present) - ok)
    for r in present:
        if r["status"] != "ok":
            log.info("  %s no.%s: %s", r["issue_date"], r["gazette_no"], r["status"])


if __name__ == "__main__":
    main()
