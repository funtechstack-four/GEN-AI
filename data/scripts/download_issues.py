"""Download the Gazette PDFs listed in gazette_issues.csv into data/raw/gazette/ (gitignored).

Skips files already on disk, waits between requests, and logs issues that can't be fetched.

    python data/scripts/download_issues.py --limit 20          # test run
    python data/scripts/download_issues.py --year 2024
    python data/scripts/download_issues.py                     # everything
"""
from __future__ import annotations

import argparse
import csv
import logging
import time

from common import ISSUES_CSV, RAW_PDF, fetch_bytes, get_logger, pdf_name

log = get_logger("download_issues")
logging.getLogger("scrapling").setLevel(logging.WARNING)  # one line per file is enough


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--year", type=int, help="only this year")
    ap.add_argument("--limit", type=int, help="stop after this many issues (newest first)")
    ap.add_argument("--delay", type=float, default=1.0, help="seconds between downloads")
    args = ap.parse_args()

    with ISSUES_CSV.open(encoding="utf-8") as f:
        issues = [r for r in csv.DictReader(f) if not args.year or int(r["year"]) == args.year]
    issues.sort(key=lambda r: r["issue_date"], reverse=True)
    if args.limit:
        issues = issues[: args.limit]

    got = skipped = failed = 0
    for i, row in enumerate(issues, 1):
        dest = RAW_PDF / row["year"] / pdf_name(row["issue_date"], row["gazette_no"])
        if dest.exists() and dest.stat().st_size > 0:
            skipped += 1
            continue
        body = fetch_bytes(row["pdf_url"], log)
        time.sleep(args.delay)
        # Some Kenya Law files have bytes before the header, which PDF readers accept.
        if not body or b"%PDF" not in body[:1024]:
            if body:
                log.warning("not a PDF (%d bytes): %s", len(body), row["pdf_url"])
            failed += 1
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(body)
        got += 1
        log.info("[%d/%d] %s (%d KB)", i, len(issues), dest.name, len(body) // 1024)
    log.info("done: %d downloaded, %d already on disk, %d failed", got, skipped, failed)


if __name__ == "__main__":
    main()
