"""Split downloaded Gazette PDFs into notices and write the land notices to gazette_notices.parquet.

Rule-based first pass ("rules-v1"): notice type, parcel references, named parties and the
objection period are pulled with regexes. raw_text is kept exactly as PyMuPDF reads it, so it
stays the source the Evidence Critic checks quotes against. Nemotron refines type/parties later.

    python data/scripts/extract_notices.py
    python data/scripts/extract_notices.py --year 2024 --limit 20
"""
from __future__ import annotations

import argparse
import collections
import re

import pyarrow as pa
import pyarrow.parquet as pq
import pymupdf

from common import EXTRACTS, NOTICES_PARQUET, RAW_PDF, get_logger, read_issues
from verify_pdfs import read_masthead

# Scanned issues OCR with spaces inside words: "G a zet t e N o t ice N o . 799 2".
NOTICE_RE = re.compile(r"G\s?A\s?Z\s?E\s?T\s?T\s?E\s+N\s?O\s?T\s?I\s?C\s?E\s*\.?\s*N\s?[O0]\s?\.?\s*(\d(?:\s?\d){2,4})", re.I)

# A notice is "land" when its heading names one of these.
LAND_MARKERS = (
    "LAND REGISTRATION ACT", "REGISTERED LAND ACT", "REGISTRATION OF TITLES ACT",
    "LAND TITLES ACT", "GOVERNMENT LANDS ACT", "SECTIONAL PROPERTIES ACT",
    "THE LAND ACT", "NATIONAL LAND COMMISSION", "SUCCESSION CAUSE", "LOSS OF TITLE DEEDS",
)
# Checked against the notice title first, then the opening text; first match wins.
# Transfer comes before succession: transfer notices often cite "Succession Cause No. ...".
TYPE_RULES = (
    ("lost_title", ("ISSUE OF A NEW", "ISSUE OF NEW", "ISSUE OF A PROVISIONAL", "ISSUE OF A REPLACEMENT",
                    "ISSUE OF REPLACEMENT", "ISSUE OF A CERTIFICATE", "LOSS OF", "PROVISIONAL CERTIFICATE")),
    ("transfer", ("REGISTRATION OF INSTRUMENT", "TRANSMISSION", "TRANSFER")),
    ("compulsory_acquisition", ("INTENTION TO ACQUIRE", "COMPULSORY ACQUISITION", "ACQUISITION OF LAND",
                                "INQUIRY", "NATIONAL LAND COMMISSION")),
    ("succession", ("SUCCESSION CAUSE",)),
    ("change_of_name", ("CHANGE OF NAME",)),
)

# "title No. Kajiado/Kaputiei South/2645", "under title Loc.19/Kiawambogo/1019",
# "land known as Kaptagat/Lotonyok Block 5 (Ngeleltarit)/661", "L.R. No. 209/12345",
# "title Nos. Miti Mingi/Mbaruk Block 5/4145, 4146 and 4147". Names may wrap across lines.
PARCEL_RE = re.compile(
    r"(?:(?:title|lease|parcel|plot|land reference|grant|sub-?division|portion|L\.\s?R\.|I\.\s?R\.|C\.\s?R\.)"
    r"\s+(?:Nos?|Numbers?)\.?\s*:?"
    r"|under\s+title(?:\s+(?:Nos?|Numbers?)\.?)?|known\s+as)\s*"
    r"((?:[A-Za-z0-9][^/,;:\n]{0,45}?(?:\n[^/,;:\n]{0,30}?){0,2}\s?/\s?)+[A-Za-z.]{0,3}\s?\d+[A-Za-z]*|\d{3,7})"
    r"((?:\s*(?:,|and|&)\s*\d+[A-Za-z]?\b)*)"
)


def parcel_refs(body: str) -> list[str]:
    refs = set()
    for ref, extra in PARCEL_RE.findall(body):
        ref = _clean(ref)
        refs.add(ref)
        prefix = ref.rsplit("/", 1)[0] + "/" if "/" in ref else ""
        refs.update(prefix + n for n in re.findall(r"\d+[A-Za-z]?", extra))
    return sorted(refs)
PARTY_RE = re.compile(
    r"WHEREAS\s+(?:the\s+(?:late\s+)?)?(.{3,160}?)"
    r"(?=\s*\(ID|\s*\(deceased|,\s*of\s|,\s*as\s|,?\s+(?:is|are|was|were)\s+(?:the\s+)?registered|,\s*both\s|,\s*all\s)",
    re.S,
)
ESTATE_RE = re.compile(r"estate of\s+(?:the\s+late\s+)?(.{3,80}?)(?:,|\s+(?:late of|who died|deceased))", re.S | re.I)
DAYS_RE = re.compile(r"expiration of\s+(?:[a-z\-\s]+?)?\(?(\d{1,3})\)?\s*days", re.I)
DATED_RE = re.compile(r"Dated\s+(?:the\s+)?(\d{1,2}(?:st|nd|rd|th)?\s+\w+,?\s+\d{4})")

log = get_logger("extract_notices")


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip(" ,.")


def _squash(s: str) -> str:
    """Upper-case with all whitespace removed, so spaced OCR text still matches."""
    return re.sub(r"\s+", "", s).upper()


def is_land(head: str) -> bool:
    sq = _squash(head)
    return any(_squash(k) in sq for k in LAND_MARKERS)


def classify(head: str, title: str = "") -> str:
    for text in (title, head):
        sq = _squash(text)
        for kind, keys in TYPE_RULES:
            if sq and any(_squash(k) in sq for k in keys):
                return kind
    return "other"


def heading_lines(text: str) -> tuple[str, str]:
    """Return (act, title) from the first few upper-case lines of a notice."""
    act = title = ""
    for line in (l.strip() for l in text.splitlines()[:8]):
        if not line or line.startswith("(") or not line.isupper():
            continue
        if not act and "ACT" in line:
            act = line
        elif not title:
            title = line
    return act, title


def notices_in_pdf(path, catalogue_date: str, gazette_no: str, pdf_url: str):
    doc = pymupdf.open(path)
    pages = [p.get_text() for p in doc]
    # The date printed on the masthead wins: Kenya Law's catalogue is off for a few issues.
    issue_date = (read_masthead(pages[0])[1] if pages else None) or catalogue_date
    starts, full = [], ""
    for page_text in pages:
        starts.append(len(full))
        full += page_text
    page_of = lambda off: max(i for i, s in enumerate(starts) if s <= off) + 1

    matches = list(NOTICE_RE.finditer(full))
    seen: set[str] = set()
    for m, nxt in zip(matches, matches[1:] + [None]):
        notice_no = re.sub(r"\s", "", m.group(1))
        if notice_no in seen:
            continue
        seen.add(notice_no)
        body = full[m.end(): nxt.start() if nxt else len(full)].strip()
        head = body[:400]
        if not is_land(head):
            continue
        act, title = heading_lines(body)
        notice_type = classify(head, title)
        parties = [_clean(p) for p in PARTY_RE.findall(body)]
        if notice_type == "succession":
            parties += [_clean(p) for p in ESTATE_RE.findall(body)]
        days = DAYS_RE.search(body)
        dated = DATED_RE.search(body)
        page = page_of(m.start())
        yield {
            "notice_id": f"{issue_date}:{notice_no}",
            "issue_date": issue_date,
            "catalogue_date": catalogue_date,
            "gazette_no": gazette_no,
            "notice_no": notice_no,
            "notice_type": notice_type,
            "act": act,
            "notice_title": title,
            "parcel_refs": parcel_refs(body),
            "parties": sorted(set(p for p in parties if p)),
            "objection_days": int(days.group(1)) if days else None,
            "notice_dated": dated.group(1) if dated else None,
            "raw_text": full[m.start(): nxt.start() if nxt else len(full)].strip(),
            "page": page,
            "source_url": f"{pdf_url}#page={page}",
            "extractor": "rules-v1",
        }


SCHEMA = pa.schema([
    ("notice_id", pa.string()), ("issue_date", pa.string()), ("catalogue_date", pa.string()),
    ("gazette_no", pa.string()),
    ("notice_no", pa.string()), ("notice_type", pa.string()), ("act", pa.string()),
    ("notice_title", pa.string()), ("parcel_refs", pa.list_(pa.string())),
    ("parties", pa.list_(pa.string())), ("objection_days", pa.int32()),
    ("notice_dated", pa.string()), ("raw_text", pa.string()), ("page", pa.int32()),
    ("source_url", pa.string()), ("extractor", pa.string()),
])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--year", type=int)
    ap.add_argument("--limit", type=int, help="only the newest N PDFs")
    args = ap.parse_args()

    pdfs = sorted(RAW_PDF.glob(f"{args.year or '*'}/*.pdf"), key=lambda p: p.name, reverse=True)
    if args.limit:
        pdfs = pdfs[: args.limit]
    if not pdfs:
        raise SystemExit(f"no PDFs under {RAW_PDF}; run download_issues.py first")

    issues = read_issues()
    rows, failed = [], 0
    for path in pdfs:
        issue = issues.get(path.name)
        if not issue:
            log.warning("skipping %s: not in %s", path.name, "gazette_issues.csv")
            continue
        issue_date, gazette_no, url = issue["issue_date"], issue["gazette_no"], issue["pdf_url"]
        try:
            found = list(notices_in_pdf(path, issue_date, gazette_no, url))
        except Exception as exc:  # one bad PDF must not stop the run
            log.error("failed %s: %s: %s", path.name, type(exc).__name__, exc)
            failed += 1
            continue
        rows += found
        log.info("%s no.%s: %d land notices", issue_date, gazette_no, len(found))

    EXTRACTS.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(rows, schema=SCHEMA), NOTICES_PARQUET, compression="zstd")

    by_type = collections.Counter(r["notice_type"] for r in rows)
    lost = [r for r in rows if r["notice_type"] == "lost_title"]
    with_parcel = sum(1 for r in lost if r["parcel_refs"])
    log.info("wrote %d notices from %d PDFs (%d failed) to %s", len(rows), len(pdfs), failed, NOTICES_PARQUET.name)
    log.info("by type: %s", dict(by_type.most_common()))
    if lost:
        log.info("lost_title notices with a parcel ref: %d/%d (%.0f%%)", with_parcel, len(lost), 100 * with_parcel / len(lost))


if __name__ == "__main__":
    main()
