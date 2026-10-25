"""Builds data/extracts/judgments.csv from a hand-picked list of Kenya Law judgments.

Each pick is a judgment URL path, the parcel(s) it's about, a flag and an excerpt chosen by
hand. The script keeps only the judgment body as raw_text (whitespace collapsed) and refuses
to write the CSV if an excerpt isn't in that text word for word, or a parcel isn't found in
it, so the Evidence Critic can check judgment quotes the same way it checks Gazette quotes.

Source and licence: judgments are published by Kenya Law (National Council for Law
Reporting, new.kenyalaw.org) and reused here under CC BY-NC 4.0, credited to NCLR, for a
non-commercial hackathon project. Kenya Law's terms prohibit automated scraping and bulk
extraction without an NCLR licence; this fetches 14 hand-picked pages once each and caches
them in data/raw/judgments/ (gitignored). National ID numbers in the text are masked.
Party names are as published; a judgment is about the parcel and the dispute, not a
finding about a seller in our demo.

Run:  python data/scripts/build_judgments.py
"""
import csv
import html
import re
import sys
import time
import urllib.request
from pathlib import Path

DATA = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DATA))
import normalizer  # noqa: E402

OUT = DATA / "extracts" / "judgments.csv"
CACHE = DATA / "raw" / "judgments"  # gitignored, so each page is downloaded once
BASE = "https://new.kenyalaw.org"
UA = {"User-Agent": "Mozilla/5.0 (GEN-AI hackathon data build)"}

# (judgment path, parcels as written in the judgment, flag, excerpt copied from the judgment)
PICKS: list[tuple[str, list[str], str, str]] = [
    ("/akn/ke/judgment/keelc/2024/567/eng@2024-02-08", ["L.R 209/8298"], "parallel_title_revoked",
     "An order be and is hereby issued compelling the 2nd Defendant to revoke any other titles pertaining and "
     "touching on the parcel of land contained under deed plan no 93986 being L.R 209/8298 registered as Grant "
     "I.R No. 34676."),
    ("/akn/ke/judgment/keelc/2023/21372/eng@2023-11-02", ["Dagoretti/Kinoo/2800"], "dealings_restrained",
     "The Court directs that the defendants, either acting individually or jointly are barred from any dealings "
     "in respect to the suit property Dagoretti/Kinoo/2800 without involving the Plaintiff."),
    ("/akn/ke/judgment/keelc/2024/13561/eng@2024-11-22", ["Kiambogo/Miroreni/Block 1/253"],
     "fraudulent_lost_title_notice",
     "In this case, the instrument of fraud was the Gazette Notice No 6686 dated 17th June 2011"),
    ("/akn/ke/judgment/keelc/2026/430/eng@2026-01-29", ["Kajiado/Kitengela/2491"], "fraudulent_lost_title_notice",
     "Kajiado/Kitengela/2491) to be gazetted as lost via a notice dated 25th March 2013, despite the land having "
     "been subdivided and sold decades prior to that date."),
    ("/akn/ke/judgment/keelc/2022/2870/eng@2022-05-11", ["Kikuyu/Kikuyu Block 1/903"], "duplicate_title_cancelled",
     "An order be and is hereby issued directing the 1 st Defendant to surrender the duplicate certificate of "
     "lease for cancellation within 10 days from the date of the judgment"),
    ("/akn/ke/judgment/keelc/2022/3884/eng@2022-07-28", ["Njoro/Ngata Block 27/21"],
     "reconstructed_register_title_cancelled",
     "the records relating to the 4 th defendant’s ownership were reconstructed in 2018 when the 4 th defendant "
     "applied for the reconstruction since she had lost the original title and was issued with a provisional "
     "title in January 2019."),
    ("/akn/ke/judgment/keelc/2022/15468/eng@2022-12-20", ["West Mugirango/Nyamaiya/3730"],
     "transfer_during_lost_title_notice",
     "they discovered that the land had been transferred to the 1 st Defendant when they went to the Lands "
     "Office Nyamira for the replacement of the Title Deed at the expiry of the Notice period of the "
     "Gazettement of loss."),
    ("/akn/ke/judgment/keelc/2023/20280/eng@2023-09-28", ["Thika/mun/block19/778"], "lost_title_notice_disputed",
     "regarding the Gazette Notices by which his original title was allegedly announced as lost to pave the way "
     "for issuance of a new title to the Plaintiff."),
    ("/akn/ke/judgment/keelc/2026/156/eng@2026-01-22", ["Kwale/DianiS.S./2248", "Kwale/DianiS.S./2249"],
     "register_reconstruction",
     "Upon the lapse of the statutory sixty (60) days, and in the absence of any objection, she lodged "
     "applications for reconstruction of the two land registers and replacement of the lost title deed."),
    ("/akn/ke/judgment/keelc/2026/3623/eng@2026-06-04", ["Tetu/Unjiru/1303"], "lost_title_declared_by_holder",
     "declared the suit property's title as lost and proceeded to procure one in the name of the deceased "
     "plaintiff."),
    ("/akn/ke/judgment/keelc/2022/12647/eng@2022-05-12", ["Gatarakwa/Gatarakwa 1/176"], "fraudulent_registration",
     "A declaration that the registration of the defendants as the owners of the parcel of land known as "
     "Gatarakwa/Gatarakwa 1/176 (the suit property) was illegal, unlawful and fraudulent."),
    ("/akn/ke/judgment/keelc/2025/7318/eng@2025-10-16", ["Athi River/Athi River Block 5/164"],
     "succession_sale_disputed",
     "the court had gazetted the temporary grant for six months and a copy of the same given to all family "
     "members and none of them complained."),
    ("/akn/ke/judgment/keelc/2022/1821/eng@2022-02-03", ["Thika Municipality Block 19/813"],
     "sale_without_original_title",
     "the agreement shows that the vendor did not have the original title deed"),
    ("/akn/ke/judgment/keelc/2023/19994/eng@2023-09-21", ["Nandi/Kiminda/1388"], "sale_without_original_title",
     "the original certificate of title was lost at the time of preparation of the agreement for sale."),
]


def fetch(path: str) -> str:
    cached = CACHE / (path.strip("/").replace("/", "_").replace("@", "_") + ".html")
    if cached.exists():
        return cached.read_text(encoding="utf-8")
    for attempt in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(BASE + path, headers=UA), timeout=60) as r:
                page = r.read().decode("utf-8", "replace")
            CACHE.mkdir(parents=True, exist_ok=True)
            cached.write_text(page, encoding="utf-8")
            time.sleep(2)  # one page at a time, gently
            return page
        except OSError as err:
            print(f"  retry {attempt + 1}: {err}")
            time.sleep(3)
    raise RuntimeError(f"couldn't download {path}")


def clean(fragment: str) -> str:
    text = re.sub(r"<(script|style)\b.*?</\1>", " ", fragment, flags=re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


_ID_RE = re.compile(r"(?i)(\b(?:I\.?\s?D\.?|identity card|national id)\s*(?:card\s*)?(?:no\.?|number|nos\.?)?\s*[:.]?\s*)"
                    r"(\d[\d/]{4,})")


def mask_ids(text: str) -> str:
    """National ID numbers as published (e.g. "ID no. 1234567/89") become "ID no. xxxxxxx"."""
    return _ID_RE.sub(lambda m: m.group(1) + "x" * len(m.group(2)), text)


def body_text(page: str) -> str:
    """The judgment itself, without the site's menus. Newer pages use <la-akoma-ntoso>,
    older ones a div with id="document_content"."""
    akn = re.search(r"<la-akoma-ntoso\b.*?</la-akoma-ntoso>", page, re.S)
    if akn:
        return clean(akn.group(0))
    start = page.find('id="document_content"')
    if start == -1:
        raise ValueError("can't find the judgment text on the page")
    start = page.index(">", start) + 1
    ends = [page.find(marker, start) for marker in ('<div class="tab-pane"', 'id="saved-document-modal"', "<footer")]
    return clean(page[start:min(e for e in ends if e != -1)])


COURTS = {"KEELC": "Environment and Land Court", "KEHC": "High Court", "KECA": "Court of Appeal",
          "KESC": "Supreme Court"}
_LABELS = ("Alternative citations", "Judges", "Judgment date", "Language", "Court station", "Case action",
           "Citation", "Case number", "Outcome", "Attorneys", "Summary", "Flynote", "Judgment summary")
_STOP = r"(?= (?:" + "|".join(_LABELS) + r")\b|$)"


def metadata(page: str) -> dict:
    h1 = re.search(r"<h1[^>]*>(.*?)</h1>", page, re.S)
    title = clean(h1.group(1)) if h1 else ""
    m = re.match(r"^(?P<parties>.+?) (?P<citation>\[\d{4}\] (?P<code>[A-Z]+) \d+ \(KLR\))", title)
    cut = [i for i in (page.find("<la-akoma-ntoso"), page.find('id="document_content"')) if i != -1]
    info = clean(page[: min(cut)] if cut else page)

    def field(label: str) -> str:
        found = re.search(rf"\b{label} (.+?)" + _STOP, info)
        return found.group(1).strip() if found else ""

    date = re.search(r"Judgment date (\d{1,2} \w+ \d{4})", info)
    if not (m and field("Case number") and date):
        raise ValueError(f"can't read the case details for {title!r}")
    return {"parties": m["parties"], "citation": m["citation"], "case_no": field("Case number"),
            "date": date.group(1), "court": field("Court station") or COURTS.get(m["code"], m["code"]),
            "outcome": field("Outcome")}


def main():
    rows = []
    for path, parcels, flag, excerpt in PICKS:
        page = fetch(path)
        try:
            text = mask_ids(body_text(page))
            meta = metadata(page)
        except ValueError as err:
            sys.exit(f"{path}: {err}")
        quote = re.sub(r"\s+", " ", excerpt).strip()
        if quote not in text:
            sys.exit(f"excerpt not found word for word in {path}: {quote[:80]!r}")
        ids = []
        for parcel in parcels:
            pid = normalizer.normalise(parcel)
            # parcels are listed as the judgment writes them, so an exact match also counts
            # (find_in_text misses a few spellings, e.g. "Kwale/DianiS.S./2248")
            if pid is None or not (parcel in text or normalizer.find_in_text(pid, text)):
                sys.exit(f"parcel {parcel!r} not found in {path}")
            ids.append(pid.key)
        rows.append({
            "judgment_id": meta["citation"],
            "case_no": meta["case_no"],
            "court": meta["court"],
            "decision_date": meta["date"],
            "outcome": meta["outcome"],
            "parties": meta["parties"],
            "parcel_ids": ";".join(ids),
            "flag": flag,
            "excerpt": quote,
            "url": BASE + path,
            "source": "Kenya Law (NCLR), CC BY-NC 4.0",
            "raw_text": text,
        })
        print(f"ok {meta['citation']}: {';'.join(ids)} | {meta['outcome']}")
    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {len(rows)} judgments to {OUT}")


if __name__ == "__main__":
    main()
