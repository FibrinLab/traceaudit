"""Trace segmentation into typed claims (spec 04 §1)."""
from __future__ import annotations

import re

from . import extract
from . import lexicon as lex_mod
from .lexicon import Lexicon
from .schema import Claim
from .textutil import split_sentences, strip_span

_PARA = re.compile(r"\n\s*\n")
_STRUCT = re.compile(r"^[ \t]*(?:#+\s+|[-*•]\s+|\d+[.)]\s+|\|)", re.M)
_ARROW = re.compile(r"→|=>|->|⇒")
_MIN_WORD_CHARS = 3


def _units(text: str) -> list[tuple[int, int]]:
    """Paragraph -> structural line -> sentence -> arrow clause spans."""
    units: list[tuple[int, int, int]] = []  # (start, end, paragraph_id)
    pos = 0
    pid = 0
    paragraphs: list[tuple[int, int]] = []
    for m in _PARA.finditer(text):
        paragraphs.append((pos, m.start()))
        pos = m.end()
    paragraphs.append((pos, len(text)))
    for ps, pe in paragraphs:
        if pe <= ps or not text[ps:pe].strip():
            continue
        # structural lines
        line_starts = [ps]
        for m in _STRUCT.finditer(text, ps, pe):
            if m.start() != ps:
                line_starts.append(m.start())
        line_starts.append(pe)
        for a, b in zip(line_starts, line_starts[1:]):
            # drop the bullet/number prefix
            m = _STRUCT.match(text, a, b)
            a2 = m.end() if m else a
            for s, e in split_sentences(text, a2, b):
                # arrows
                last = s
                for am in _ARROW.finditer(text, s, e):
                    units.append((last, am.start(), pid))
                    last = am.end()
                units.append((last, e, pid))
        pid += 1
    out = []
    for s, e, p in units:
        s2, e2 = strip_span(text, s, e)
        s2, e2 = _trim_punct(text, s2, e2)
        if e2 > s2 and len(re.findall(r"\w", text[s2:e2])) >= _MIN_WORD_CHARS:
            out.append((s2, e2, p))
    return out


def _trim_punct(text: str, s: int, e: int) -> tuple[int, int]:
    while s < e and text[s] in "*_`\"'“”([":
        s += 1
    while e > s and text[e - 1] in "*_`\"'“”":
        e -= 1
    return strip_span(text, s, e)


def classify(text: str, assertions, entities, lx: Lexicon) -> tuple[str, list[str]]:
    """Ordered typing rules [PRE-REG], spec 04 §1.2."""
    flags: list[str] = []
    low = text.lower()
    if lx.has_phrase("question", text):
        return "other", ["question"]
    if lx.has_phrase("conditional", " " + low + " "):
        return "inferential", ["conditional"]
    has_knowledge = lx.has_phrase("knowledge", text)
    has_patient = lx.has_phrase("patient_reference", text)
    generic_subject = bool(entities) or re.search(r"\b(cases|lymphomas?|leukaemias?|leukemias?|neoplasms?|entit(y|ies))\b", low)
    if has_knowledge and not has_patient and generic_subject:
        return "knowledge", flags
    polar = [a for a in assertions if a.polarity]
    has_inf = lx.has_phrase("inference", text) or bool(entities)
    if polar:
        if has_inf:
            flags.append("has_inference")
        return "factual", flags
    if has_inf:
        return "inferential", flags
    return "other", flags


def segment(reasoning: str, trace_key: str = "", lexicon: Lexicon | None = None) -> list[Claim]:
    lx = lexicon or lex_mod.load()
    if not reasoning:
        return []
    all_assertions = extract.extract_assertions(reasoning, lx)
    all_entities = lx.find_entities(reasoning)
    claims: list[Claim] = []
    for cid, (s, e, pid) in enumerate(_units(reasoning)):
        text = reasoning[s:e]
        asserts = [a for a in all_assertions if s <= a.start < e]
        ents = [m for m in all_entities if s <= m.start < e]
        ctype, flags = classify(text, asserts, ents, lx)
        warnings = sorted({w for a in asserts for w in a.warnings})
        claims.append(Claim(trace_key=trace_key, claim_id=cid, paragraph_id=pid, start=s, end=e, text=text,
                            type=ctype, flags=flags, assertions=asserts if ctype == "factual" else asserts,
                            entities=sorted({m.entity for m in ents}), warnings=warnings))
    return claims


def trace_conclusion(claims: list[Claim], reasoning: str, lx: Lexicon) -> str | None:
    """Heuristic trace conclusion entity (spec 04 §1.3)."""
    conclusion_phr = lx.phrases.get("conclusion", [])
    last_named = None
    for c in claims:
        if c.entities:
            last_named = c
    for c in reversed(claims):
        if c.type == "inferential" and c.entities and any(p in c.text.lower() for p in conclusion_phr):
            ents = lx.find_entities(c.text)
            return ents[-1].entity if ents else c.entities[-1]
    if last_named:
        ents = lx.find_entities(last_named.text)
        return ents[-1].entity if ents else last_named.entities[-1]
    return None
