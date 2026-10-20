"""Text utilities shared by extract and segment (stdlib only).

All functions report character offsets into the *original* string. Normalisation
used for matching is length-preserving (one character maps to one character).
"""
from __future__ import annotations

import re

_DASHES = {"−": "-", "–": "-", "—": "-", "‑": "-", "‐": "-", " ": " ",
           "×": "x", "’": "'", "“": '"', "”": '"'}
_TRANS = str.maketrans(_DASHES)


def normalise(text: str) -> str:
    """Lowercase, map Unicode dashes/nbsp to ASCII. Length-preserving."""
    out = text.translate(_TRANS).lower()
    assert len(out) == len(text)
    return out


_ABBREV = ("e.g.", "i.e.", "vs.", "cf.", "approx.", "dr.", "fig.", "no.", "et al.", "ca.", "al.",
           "prof.", "mr.", "mrs.", "ms.", "inc.", "etc.")
# a sentence may also start with cytogenetic / HGVS notation in lower case: t(11;14), del(17p), p.V600E, c.1799T>A
# model-written traces may start sentences in lower case too; abbreviations are guarded below
_SENT_END = re.compile(r'[.!?]+(?=\s+(?:[A-Za-z0-9"(\*\-•]|$))|[.!?]+$')


def split_sentences(text: str, start: int = 0, end: int | None = None) -> list[tuple[int, int]]:
    """Split text[start:end] into sentence spans (absolute offsets, stripped).

    Protects common abbreviations, decimals and single-letter initials.
    """
    if end is None:
        end = len(text)
    seg = text[start:end]
    low = seg.lower()
    spans: list[tuple[int, int]] = []
    last = 0
    for m in _SENT_END.finditer(seg):
        pos = m.end()
        before = low[:pos]
        # decimals like 12.3 -> the regex requires whitespace+uppercase after, so fine; guard abbreviations
        if any(before.endswith(a) for a in _ABBREV):
            continue
        # single capital initial "J. Smith"
        if re.search(r"(?:^|\s)[A-Za-z]\.$", seg[:pos]):
            continue
        spans.append((last, pos))
        last = pos
    if last < len(seg):
        spans.append((last, len(seg)))
    out = []
    for a, b in spans:
        s, e = _strip_span(seg, a, b)
        if e > s:
            out.append((start + s, start + e))
    return out


def _strip_span(text: str, a: int, b: int) -> tuple[int, int]:
    while a < b and text[a].isspace():
        a += 1
    while b > a and text[b - 1].isspace():
        b -= 1
    return a, b


def strip_span(text: str, a: int, b: int) -> tuple[int, int]:
    return _strip_span(text, a, b)


_WORD = re.compile(r"[A-Za-z0-9]")


def is_word_char(ch: str) -> bool:
    return bool(_WORD.match(ch))


def word_bounded(text: str, start: int, end: int) -> bool:
    """True if text[start:end] is not glued to alphanumerics on either side."""
    if start > 0 and is_word_char(text[start - 1]):
        return False
    if end < len(text) and is_word_char(text[end]):
        return False
    return True


def sha256_text(text: str) -> str:
    import hashlib
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path) -> str:
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()
