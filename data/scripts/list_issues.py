"""List Kenya Gazette issues for the given years and write data/extracts/gazette_issues.csv.

Source: kenyalaw.org/gazettes (read with Scrapling). Each issue's PDF is at <issue page>/source.pdf.
We don't use archive.gazettes.africa: its robots.txt disallows automated access to /archive/.
Supplements carry no notices and are skipped.

    python data/scripts/list_issues.py --years 2022 2023 2024
"""
from __future__ import annotations

import argparse
import csv
import re

from scrapling.fetchers import Fetcher

from common import EXTRACTS, ISSUES_CSV, get_logger

LISTING = "https://kenyalaw.org/gazettes/{year}"
BASE = "https://kenyalaw.org"
# /akn/ke/officialGazette/[<kind>/]<YYYY-MM-DD>/<number>/eng@<YYYY-MM-DD>
HREF_RE = re.compile(r"^/akn/ke/officialGazette/(?:([a-z-]+)/)?(\d{4}-\d{2}-\d{2})/([^/]+)/eng@[\d-]+$")
SKIP_KINDS = {"government-gazette-acts-supplement", "government-gazette-legislative-supplement",
              "government-gazette-bills-supplement"}

log = get_logger("list_issues")


def list_year(year: int) -> list[dict]:
    page = Fetcher.get(LISTING.format(year=year), timeout=60)
    if page.status != 200:
        raise RuntimeError(f"{LISTING.format(year=year)} returned HTTP {page.status}")
    rows = {}
    for href in page.css('a[href*="/akn/ke/officialGazette/"]::attr(href)').getall():
        m = HREF_RE.match(str(href).split("#")[0])
        if m and m.group(1) not in SKIP_KINDS:
            _, date, no = m.groups()
            rows[(date, no)] = {"year": year, "issue_date": date, "gazette_no": no,
                                "pdf_url": f"{BASE}{m.group(0)}/source.pdf"}
    log.info("%d: %d issues", year, len(rows))
    return sorted(rows.values(), key=lambda r: (r["issue_date"], r["gazette_no"]))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--years", type=int, nargs="+", default=[2022, 2023, 2024])
    args = ap.parse_args()

    rows = [r for y in args.years for r in list_year(y)]
    EXTRACTS.mkdir(parents=True, exist_ok=True)
    with ISSUES_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["year", "issue_date", "gazette_no", "pdf_url"])
        w.writeheader()
        w.writerows(rows)
    log.info("wrote %d issues to %s", len(rows), ISSUES_CSV.name)


if __name__ == "__main__":
    main()
