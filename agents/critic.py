"""Evidence critic: exact parcel identity and verbatim source validation."""
from __future__ import annotations

import re
from typing import Any

from agents.excerpt import snap_to_words
from data import normalizer


def normalized_quote(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("ﬁ", "fi").replace("ﬂ", "fl")).strip()


def matches_parcel(parcel: str, row: dict[str, Any], text: str) -> bool:
    refs = row.get("parcel_refs") or row.get("parcel_ids") or []
    if isinstance(refs, str):
        refs = [refs]
    return bool(normalizer.refs_match(parcel, refs) or normalizer.find_in_text(parcel, text))


def quote_for(parcel: str, text: str) -> str:
    hits = normalizer.find_in_text(parcel, text)
    if not hits:
        return ""
    hit = hits[0]
    # A short literal source window gives the reader context while remaining provably verbatim.
    start = max(0, hit.start() - 120)
    end = min(len(text), hit.end() + 220)
    return snap_to_words(text, start, end)


def critic_claim(parcel: str, row: dict[str, Any], claim: dict[str, Any]) -> tuple[bool, str]:
    source_text = str(row.get("raw_text") or row.get("excerpt") or "")
    if not matches_parcel(parcel, row, source_text):
        return False, "source does not identify this exact parcel"
    quote = claim.get("quote", "")
    if not quote or normalized_quote(quote) not in normalized_quote(source_text):
        return False, "quote is not a verbatim substring of the source"
    return True, ""
