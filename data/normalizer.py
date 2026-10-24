"""Parcel ID normaliser and cancelled-serial check for the Intake Normaliser agent.

One parcel is written many ways (``LR 209/3466``, ``L.R. No. 209/3466``, ``Nairobi/Block 82/288``,
OCR text split over lines). ``normalise`` turns free text into one ``ParcelId`` whose ``key`` is
``SCHEME:SECTION/NUMBER``; two spellings are the same parcel only when their keys are equal.

Schemes: ``LR`` (Land Reference, numeric section such as ``209``), ``IR`` (Index/Grant ``I.R.``),
``CR`` (Certificate ``C.R.``) and ``RL`` (Registered Land / Land Registration Act section titles
such as ``Nairobi/Block 82``). Numbers are never fuzzy-matched: ``288`` is not ``2288``, ``2880``
or ``289``.

Pure stdlib (pyarrow only for ``--coverage``). No network, no LLM.

    python data/normalizer.py --coverage
"""
from __future__ import annotations

import argparse
import csv
import dataclasses
import functools
import pathlib
import re
import string
import sys
from typing import Iterable

ROOT = pathlib.Path(__file__).resolve().parents[1]
EXTRACTS = ROOT / "data" / "extracts"
NOTICES_PARQUET = EXTRACTS / "gazette_notices.parquet"
CANCELLED_CSV = EXTRACTS / "cancelled_serials.csv"

MAX_INPUT = 20_000  # longer input is cut; keeps every call bounded

# --------------------------------------------------------------------------- parsing

_QUOTES = "'\"`‘’“”�"
# Manyatta 'A', Manyatta (A), Manyatta "A", Manyatta �A� -> Manyatta A (the letter is part of the name).
_LETTER_SUFFIX_RE = re.compile(rf"\s*[{_QUOTES}(]\s?([A-Za-z])\s?[{_QUOTES})]")
# Multi-char parentheticals such as (EATEC), (Orig. No. 2/222), (Ha.) are dropped.
_PAREN_RE = re.compile(r"\([^()]*\)")
_SLASH_RE = re.compile(r"\s*/\s*")
# A parcel number: 288, 7A, T.257, T. 1890, S. 37. Anything after it is the tail.
_NUM_RE = re.compile(r"\s*((?:[A-Za-z]\.?\s?)?\d+[A-Za-z]?)(?![A-Za-z0-9])(.*)", re.S)
_NUM_ONLY_RE = re.compile(r"\s*(?:[A-Za-z]\.?\s?)?\d+[A-Za-z]?\s*[.,;:]?\s*")
# L.R. / LR / L R / I.R. / IR. / C.R. ("C. Kasipul" is a name: the R must stand alone).
_PREFIX_RE = re.compile(r"(?<![A-Za-z0-9])([LIC])\s?\.?\s?R(?![A-Za-z])\.?", re.I)
_NO_RE = re.compile(r"\s*(?:(?:N\s?o\s?s?|numbers?)(?![A-Za-z])\s?\.?\s*)+", re.I)
# Words that end a lead-in before the section name; the head keeps only text after the last one.
_SEP_RE = re.compile(
    r"[,;:&]|\d+\.\d+|\bN\s?o\s?s?\s?\.|"
    r"\b(?:and|or|known\s+as|as|on|of|under|being|title|titles|parcel|parcels|plot|plots|land|"
    r"reference|ref|no|nos|numbers?|original|orig|grant|flat|lease|portion|sub-?division|area)\b\.?",
    re.I,
)
_BLOCK_RE = re.compile(r"\bBLOCK(?![A-Z])\s*[.\-]?\s*([A-Z0-9]+)\s*\.?\s*$")
_NOT_ALNUM_RE = re.compile(r"[^A-Z0-9]")
_NUM_TOKEN = r"\d+[A-Za-z]?(?![A-Za-z0-9])(?!\.\d)"
_JOINER = r"(?:,\s*(?:and(?![A-Za-z])|&)?|&|and(?![A-Za-z]))"  # ", and" (Oxford comma) is one joiner
# ", 289" / " and 289" after a sectioned parcel: siblings in the same section ("Nairobi/Block 82/288 and 289").
_SIBLING_RE = re.compile(rf"\s*{_JOINER}\s*({_NUM_TOKEN})", re.I)
# "Nos. 1234 and 5678" right after a prefix: a list of section-less numbers.
_BARE_LIST_RE = re.compile(
    rf"\s*(?:(?:grant|original|orig)\.?\s+)?(?:(?:N\s?o\s?s?|numbers?)(?![A-Za-z])\s?\.?\s*)?"
    rf"({_NUM_TOKEN}(?:\s*{_JOINER}\s*{_NUM_TOKEN})*)",
    re.I,
)
_DIGITS_RE = re.compile(r"\d+[A-Za-z]?")
# A prefix's scope ends at ";" or a sentence end (". The"); "No.", "Loc." and "L.R." are not sentence ends.
_RESET_RE = re.compile(r";|(?:(?<![A-Za-z])|(?<=[a-z]{3}))\.\s+(?=[A-Z])")

SCHEMES = ("LR", "IR", "CR", "RL")


@dataclasses.dataclass(frozen=True)
class ParcelId:
    """Canonical parcel identity. Equality uses scheme, section and number only.

    ``section`` is the ``/``-joined canonical path (``NAIROBI/BLOCK 82``, ``209``, or ``""`` for a
    bare ``C.R. No. 1234``). ``label`` is a readable spelling kept for ``variants()``.
    """

    scheme: str
    section: str
    number: str
    label: str = dataclasses.field(default="", compare=False, repr=False)

    @property
    def key(self) -> str:
        return f"{self.scheme}:{self.section}/{self.number}" if self.section else f"{self.scheme}:{self.number}"

    def __str__(self) -> str:
        return self.key


def _squash(s: str) -> str:
    return _NOT_ALNUM_RE.sub("", s.upper())


def _readable(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip(" .,;:-")


def _cap(text: str) -> str:
    """Cut text longer than ``MAX_INPUT`` at the last whitespace before the cap, so a number is
    never split (``... LR 209/3466`` never becomes ``LR:2``)."""
    if len(text) <= MAX_INPUT:
        return text
    cut = text[:MAX_INPUT]
    ws = max(cut.rfind(" "), cut.rfind("\n"), cut.rfind("\t"), cut.rfind("\r"))
    if ws > 0:
        return cut[:ws]
    return cut.rstrip(string.ascii_letters + string.digits)


def _prep(text: str) -> str:
    s = _cap(text)
    s = _LETTER_SUFFIX_RE.sub(r" \1", s)
    s = _PAREN_RE.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip()


def _segments(raw: str) -> list[tuple[str, str]]:
    """One raw section segment -> [(key part, label part)], splitting a trailing ``BLOCK n``."""
    raw = raw.split("(", 1)[0]  # an unclosed "(" stops at the next "/"
    up = raw.upper()
    m = _BLOCK_RE.search(up)
    out = []
    if m:
        name = raw[: m.start()]
        if _squash(name):
            out.append((_squash(name), _readable(name)))
        out.append((f"BLOCK {m.group(1)}", f"Block {m.group(1)}"))
    elif _squash(raw):
        out.append((_squash(raw), _readable(raw)))
    return out


def _bare_nums(lead: str) -> list[str]:
    """Numbers of a bare list right after a prefix: ``Nos. 1234 and 5678`` -> ``["1234", "5678"]``."""
    m = _BARE_LIST_RE.match(lead)
    return _DIGITS_RE.findall(m.group(1)) if m else []


def _parse_head(head: str, scope: str | None, final: bool = False) -> tuple[list[ParcelId], str | None, str]:
    """Text before a parcel body -> (bare parcels, scheme scope for the body, first section segment).

    An ``I.R.``/``C.R.``/``L.R.`` prefix sets the scope for every parcel after it (through ``No.``,
    ``Nos.``, ``Grant`` and list joiners) until another prefix, a ``;`` or a sentence end. ``scope``
    is the scope carried from the parcel before; a prefix never reaches back. With ``final`` there is
    no body: the whole head is lead-in (``C.R. Nos. 1234 and 1235``).
    """
    bare: list[ParcelId] = []
    prefixes = list(_PREFIX_RE.finditer(head))
    chunks: list[tuple[str | None, str]] = [(None, head[: prefixes[0].start()] if prefixes else head)]
    for i, p in enumerate(prefixes):
        end = prefixes[i + 1].start() if i + 1 < len(prefixes) else len(head)
        chunks.append((p.group(1).upper() + "R", head[p.end(): end]))
    body = ""
    for i, (prefix, text) in enumerate(chunks):
        if prefix:
            scope = prefix
            nm = _NO_RE.match(text)
            text = text[nm.end():] if nm else text
        lead = text
        if i == len(chunks) - 1 and not final:
            seps = list(_SEP_RE.finditer(text))
            body = text[seps[-1].end():] if seps else text
            lead = text[: len(text) - len(body)]
        if prefix:
            bare.extend(ParcelId(scope, "", _squash(n), n) for n in _bare_nums(lead))
        if _RESET_RE.search(lead):
            scope = None
    return bare, scope, body.strip(" .,;:-(")


def _scheme(prefix: str | None, first_key: str) -> str:
    if prefix in ("IR", "CR"):
        return prefix
    return "LR" if first_key.isdigit() else "RL"


def _build(scope: str | None, first: str, raw_segs: list[str], number: str) -> ParcelId | None:
    pairs: list[tuple[str, str]] = []
    for raw in ([first] if first else []) + raw_segs:
        pairs.extend(_segments(raw))
    num = _squash(number)
    if not num:
        return None
    if not pairs:
        if scope is None:
            return None  # bare "806" has no scheme
        return ParcelId(scope, "", num, _readable(number))
    keys = [k for k, _ in pairs]
    scheme = _scheme(scope, keys[0])
    label = "/".join([lab for _, lab in pairs] + [_readable(number)])
    return ParcelId(scheme, "/".join(keys), num, label)


def _siblings(tail: str, more: bool) -> tuple[list[str], str]:
    """Leading ``, 289 and 290`` of a tail -> (sibling numbers, rest of the tail). When another
    ``/`` follows (``more``) and the list runs to the end of the tail, its last number starts the
    next parcel's section (``12716/517 and 12715/148``), so it is left in the rest."""
    found: list[tuple[str, int, int]] = []
    pos = 0
    while True:
        m = _SIBLING_RE.match(tail, pos)
        if not m:
            break
        found.append((m.group(1), pos, m.end()))
        pos = m.end()
    if found and more and not tail[pos:].strip():
        found.pop()
    if not found:
        return [], tail
    return [n for n, _, _ in found], tail[found[-1][2]:]


def normalise_all(text: str) -> list[ParcelId]:
    """Every parcel in a ref string, in order. ``Mombasa/Block XLVIII/134 and Mombasa/Block XLVII/110``
    gives two parcels; ``I.R. Nos. 13537/207 and 13537/208`` gives two ``IR`` parcels;
    ``Nairobi/Block 82/288 and 289`` gives 288 and 289 in the same section. Never raises; linear in
    the input (which is capped at ``MAX_INPUT`` chars)."""
    if not isinstance(text, str) or not text.strip():
        return []
    parts = _SLASH_RE.split(_prep(text))
    out: list[ParcelId] = []
    head, segs, skip, scope = parts[0], [], False, None
    for i in range(1, len(parts)):
        part = parts[i]
        m = _NUM_RE.match(part)
        if not m:
            segs.append(part)
            continue
        tail = m.group(2)
        more = i + 1 < len(parts)
        if not tail.strip(" .,;:") and more and _NUM_RE.match(parts[i + 1]):
            segs.append(part)  # 209/2490/45: a digit segment inside the section path
            continue
        pid = None
        # "308 (Orig No. 2/222", "10040 (Original No. 2247/6": an unclosed parenthetical names
        # older parcels; skip every parcel inside it (it never closes). Parcels before it stay.
        # "213310 (L.R. No. 12581/24" opens with a prefix: an alternate reference, so it is kept.
        if not skip and "(" in head and not _PREFIX_RE.match(head[head.index("(") + 1:].lstrip()):
            bare, scope, _ = _parse_head(head[: head.index("(")], scope, final=True)
            out.extend(bare)
            skip = True
        elif not skip:
            bare, scope, first = _parse_head(head, scope)
            out.extend(bare)
            pid = _build(scope, first, segs, m.group(1))
            if pid:
                out.append(pid)
        skip = skip or tail.strip().startswith("(")
        sibs, tail = ([], tail) if skip else _siblings(tail, more)
        if pid and pid.section:
            base = pid.label.rsplit("/", 1)[0] if pid.label else pid.section
            out.extend(ParcelId(pid.scheme, pid.section, _squash(n), f"{base}/{n}") for n in sibs)
        head, segs = tail, []
    if not segs and not skip and (len(parts) == 1 or head.strip()):
        bare, _, _ = _parse_head(head, scope, final=True)
        out.extend(bare)
    return out


def normalise(text: str) -> ParcelId | None:
    """Free-text parcel -> ``ParcelId`` (first parcel if several), or ``None``. Never raises."""
    try:
        found = normalise_all(text)
    except Exception:  # defensive: intake text is arbitrary
        return None
    return found[0] if found else None


def _as_parcel(p: ParcelId | str | None) -> ParcelId | None:
    return p if isinstance(p, ParcelId) else normalise(p) if isinstance(p, str) else None


def same_parcel(a: ParcelId | str, b: ParcelId | str) -> bool:
    """True only when both parse and their canonical keys are equal."""
    pa_, pb = _as_parcel(a), _as_parcel(b)
    return pa_ is not None and pb is not None and pa_ == pb


def variants(parcel: ParcelId | str) -> list[str]:
    """Gazette spellings of one parcel, all within its own scheme (no old-to-new conversions)."""
    p = _as_parcel(parcel)
    if p is None:
        return []
    out: list[str] = []
    if p.scheme == "RL":
        segs = p.label.split("/") if p.label else p.section.split("/") + [p.number]
        out.append("/".join(segs))
        joined = []
        for s in segs:
            if s.upper().startswith("BLOCK ") and joined:
                joined[-1] += " " + s
            else:
                joined.append(s)
        out.append("/".join(joined))
        out.append("/".join(segs).upper())
    else:
        body = f"{p.section}/{p.number}" if p.section else p.number
        letter = p.scheme[0]
        out += [f"{letter}.R. No. {body}", f"{letter}.R. {body}", f"{letter}R {body}", f"{letter}R No. {body}"]
        if p.scheme == "LR" and p.section:
            out.append(body)
    seen, uniq = set(), []
    for v in out:
        if v not in seen:
            seen.add(v)
            uniq.append(v)
    return uniq


def refs_match(parcel: ParcelId | str, refs: Iterable[str] | str | None) -> list[str]:
    """The extracted ``parcel_refs`` entries that name exactly this parcel."""
    p = _as_parcel(parcel)
    if p is None or refs is None:
        return []
    if isinstance(refs, str):
        refs = [refs]
    return [r for r in refs if isinstance(r, str) and p in normalise_all(r)]


# --------------------------------------------------------------------------- raw-text search

_FILL = rf"[\s.\-{_QUOTES}(]{{0,3}}"  # between letters of a squashed name: "CIS Mara", "K wale", "Manyatta 'A"
# Closing quote, then an optional multi-char parenthetical; "(A)" is a name suffix, never skipped.
_SEG_END = rf"[\s{_QUOTES})]{{0,3}}(?:\((?!\s?[A-Za-z]\s?\))[^()/]{{0,80}}\)?\s{{0,2}})?"
_SL = r"\s{0,2}/\s{0,2}"
_TEXT_PREFIX = r"(?<![A-Za-z0-9/]){L}\s?\.?\s?R(?![A-Za-z])\.?\s{{0,2}}(?:N\s?o\s?s?\s?\.?\s{{0,2}})?"
# Number end: no more digits, no single-letter suffix (288A), and no "/" followed by a letter, roman
# numeral or digit (288/1, and L.R. No. 1870 never hits 1870/IV/148).
_NUM_END = r"(?!\d)(?![A-Za-z](?![A-Za-z]))(?!\s?/\s?[A-Za-z0-9])"

# Words that may stand right before a section name in notice prose ("known as Nairobi Block 93/228").
_LEAD_WORDS = frozenset(
    "as no nos number numbers title titles parcel parcels plot plots land reference ref and or of on "
    "under being known grant lease portion subdivision property the in at for is was comprised "
    "described situate situated lr ir cr".split()
)
_BEFORE_WINDOW = 200  # chars of context checked before a hit


def _list_before_re(letters: str) -> re.Pattern:
    """Text ending in a ``{letters}.R.`` prefix (``No.``/``Nos.``/``Grant`` allowed) and then only
    list numbers and joiners: ``I.R. Nos. 13537/207 and `` -> the next number is under ``I.R.``."""
    return re.compile(
        rf"(?<![A-Za-z0-9])[{letters}] ?\.? ?R(?![A-Za-z])\.? ?(?:(?:grant|original|orig)\.? )?"
        r"(?:N ?o ?s? ?\.? ?)?(?:\d[\d/]*[A-Za-z]? ?(?:, ?(?:and|&)?|&|and) ?)*$",
        re.I,
    )


_LIST_BEFORE = {"L": _list_before_re("L"), "I": _list_before_re("I"), "C": _list_before_re("C")}
_IRCR_BEFORE_RE = _list_before_re("IC")
_BLOCK_BEFORE_RE = re.compile(r"block ?[.\-]? ?$", re.I)
_WORD_BEFORE_RE = re.compile(r"([A-Za-z0-9]+)([^\sA-Za-z0-9]*) $")


def _name_re(key: str) -> str:
    return _FILL.join(re.escape(c) for c in key)


def _number_re(num: str) -> str:
    m = re.fullmatch(r"([A-Z]?)(\d+)([A-Z]?)", num)
    if not m:
        return re.escape(num)
    lead, digits, suffix = m.groups()
    return (re.escape(lead) + r"[\s.]{0,2}" if lead else "") + digits + suffix


def _section_re(section: str) -> str:
    out = ""
    for i, seg in enumerate(section.split("/")):
        if seg.startswith("BLOCK "):
            sep = rf"(?:{_SL}|[\s\-]{{0,3}})" if i else ""
            num = r"\s?".join(re.escape(c) for c in seg[6:])
            out += sep + r"B\s?L\s?O\s?C\s?K[\s.\-]{0,3}" + num + r"(?![A-Za-z0-9])" + _SEG_END
        elif seg.isdigit():
            out += (_SL if i else "") + seg + r"(?!\d)"
        else:
            out += (_SL if i else "") + _name_re(seg) + _SEG_END
    return out


def _needs_prefix(p: ParcelId) -> bool:
    return p.scheme in ("IR", "CR") or (p.scheme == "LR" and not p.section)


def text_pattern(parcel: ParcelId | str) -> re.Pattern:
    """Regex for this parcel in raw notice text: whitespace/line-break tolerant, digit-bounded.

    It anchors the start (no word char or ``/`` before the first section segment) and the end
    (288 never hits 2880, 289, 288/1 or 288/IV). ``I.R.``/``C.R.`` parcels and a section-less
    ``L.R.`` match either with their prefix (group ``pfx``) or bare; a bare match counts only inside
    a list opened by that prefix. Those rules and the word-before rules need variable-width context,
    so search with ``find_in_text``, which applies them to whitespace-normalised text.
    """
    p = _as_parcel(parcel)
    if p is None:
        raise ValueError(f"not a parcel: {parcel!r}")
    num = _SL + _number_re(p.number) if p.section else _number_re(p.number)
    start = r"(?<![A-Za-z0-9/])"
    if _needs_prefix(p):
        start = rf"(?:(?P<pfx>{_TEXT_PREFIX.format(L=p.scheme[0])})|{start})"
    body = start + (_section_re(p.section) if p.section else "")
    return re.compile(body + num + _NUM_END, re.I)


def _word_ok(before: str) -> bool:
    """Reject a section hit glued to a name: ``West Nairobi/…``, ``West-Nairobi/…``. Lower-case
    prose (``the said``, ``from``), numbers (``0.1962``) and list punctuation are allowed."""
    if len(before) > 1 and before[-1] == "-" and before[-2].isalnum():
        return False
    if not before.endswith(" "):
        return True
    w = _WORD_BEFORE_RE.search(before)
    if not w:
        return True
    word, punct = w.groups()
    if punct and punct != ".":
        return True  # "Kiambu, Nairobi/Block ..." or "(Ha.) Nairobi ...": a separator, not a name
    return not (word[0].isupper() and word.lower() not in _LEAD_WORDS)


def _context_ok(p: ParcelId, m: re.Match, before: str) -> bool:
    """Apply the context rules to the (whitespace-normalised) text just before a hit."""
    if _needs_prefix(p):
        return bool(m.group("pfx")) or bool(_LIST_BEFORE[p.scheme[0]].search(before))
    if p.scheme == "LR":
        if _IRCR_BEFORE_RE.search(before) or _BLOCK_BEFORE_RE.search(before):
            return False  # I.R./C.R. prefix or list, or "Nairobi Block 209/3466"
        if _LIST_BEFORE["L"].search(before):
            return True
    return _word_ok(before)


def find_in_text(parcel: ParcelId | str, text: str) -> list[re.Match]:
    """Hits of this parcel in raw text (matches are on the original text, so ``m.group(0)`` is
    verbatim). A hit must start at the first section segment: ``West Nairobi/Block 82/288`` does
    not hit ``Nairobi/Block 82/288``; ``Nairobi Block 209/3466``, ``I.R. 209/3466`` and the second
    number of ``I.R. Nos. 13537/207 and 209/3466`` do not hit ``LR 209/3466``; a section-less
    ``L.R. No. 1234`` needs its L.R. prefix (or an L.R. list)."""
    p = _as_parcel(parcel)
    if p is None or not isinstance(text, str):
        return []
    hits = []
    for m in text_pattern(p).finditer(text):
        before = re.sub(r"\s+", " ", text[max(0, m.start() - _BEFORE_WINDOW): m.start()])
        if _context_ok(p, m, before):
            hits.append(m)
    return hits


# --------------------------------------------------------------------------- cancelled serials

@dataclasses.dataclass(frozen=True)
class SerialCheck:
    """Result of ``check_serial``. ``cancelled=True`` means the Gazette lists this title serial as
    cancelled (a STOP). ``valid=False`` means the input was not a serial or the list was unreadable."""

    serial: int | None
    valid: bool
    cancelled: bool
    gazette_notice_no: str | None = None
    gazette_no: str | None = None
    issue_date: str | None = None
    notice_date: str | None = None
    notice_title: str | None = None
    status: str | None = None
    quote: str | None = None
    source_url: str | None = None
    reason: str = ""


@functools.lru_cache(maxsize=4)
def _cancelled(path: str) -> dict[int, dict] | None:
    try:
        with open(path, encoding="utf-8", newline="") as f:
            return {int(r["serial"]): r for r in csv.DictReader(f)}
    except (OSError, csv.Error, KeyError, ValueError, UnicodeDecodeError):
        return None


def _parse_serial(serial) -> int | None:
    if isinstance(serial, bool):
        return None
    if isinstance(serial, int):
        return serial if serial >= 0 else None
    if not isinstance(serial, str):
        return None
    # "Serial No: 5253001", "No: 5253001", "No. 5,253,367", "#5253001"
    s = re.sub(r"^\s*(?:(?:serial|title)\s*:?\s*)?(?:(?:N\s?o|number)\s*[.:]?|#)?\s*", "", serial, flags=re.I)
    s = re.sub(r"[,\s]", "", s).rstrip(".")
    return int(s) if re.fullmatch(r"[0-9]{1,12}", s) else None


def check_serial(serial: int | str) -> SerialCheck:
    """Look a title serial (``5253001``, ``No. 5,253,367``, ``Serial No: 5253001``) up in ``cancelled_serials.csv``.

    The CSV is read once and cached. Never raises: bad input or a missing/unreadable CSV
    returns ``valid=False, cancelled=False`` with a ``reason``.
    """
    n = _parse_serial(serial)
    if n is None:
        return SerialCheck(None, False, False, reason="not a serial number")
    table = _cancelled(str(CANCELLED_CSV))
    if table is None:
        return SerialCheck(n, False, False, reason=f"{CANCELLED_CSV.name} missing or unreadable")
    row = table.get(n)
    if row is None:
        return SerialCheck(n, True, False)
    return SerialCheck(
        n, True, True,
        gazette_notice_no=row.get("gazette_notice_no"), gazette_no=row.get("gazette_no"),
        issue_date=row.get("issue_date"), notice_date=row.get("notice_date"),
        notice_title=row.get("notice_title"), status=row.get("status"), quote=row.get("quote"),
        source_url=row.get("source_url"),
    )


# --------------------------------------------------------------------------- CLI

def coverage(path: pathlib.Path = NOTICES_PARQUET) -> tuple[int, int]:
    """(parsed, total) over every ``parcel_refs`` entry in the notices parquet."""
    import pyarrow.parquet as pq

    rows = pq.read_table(path, columns=["parcel_refs"]).column("parcel_refs").to_pylist()
    refs = [r for refs in rows for r in (refs or [])]
    return sum(1 for r in refs if normalise(r) is not None), len(refs)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--coverage", action="store_true", help="parse rate over gazette_notices.parquet")
    ap.add_argument("text", nargs="*", help="parcel text to normalise")
    args = ap.parse_args(argv)
    if args.coverage:
        ok, total = coverage()
        rate = ok / total if total else 0.0
        print(f"parsed {ok}/{total} parcel refs ({rate:.1%})")
        return 0 if rate >= 0.85 else 1
    for t in args.text:
        p = normalise(t)
        print(f"{t!r} -> {p.key if p else None}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
