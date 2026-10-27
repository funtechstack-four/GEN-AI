"""Verbatim excerpts that start and end on whole words."""
from __future__ import annotations


def snap_to_words(text: str, start: int, end: int) -> str:
    """Return text[start:end], moved inward so it never begins or ends mid-word.

    The result is still an exact slice of the source, so the critic's verbatim
    check is unaffected; only the cut points move to the nearest whitespace.
    """
    start, end = max(0, start), min(len(text), end)
    if 0 < start < end and not text[start - 1].isspace():
        for i in range(start, end):
            if text[i].isspace():
                start = i + 1
                break
    if start < end < len(text) and not text[end].isspace():
        for i in range(end - 1, start, -1):
            if text[i].isspace():
                end = i
                break
    return text[start:end].strip()
