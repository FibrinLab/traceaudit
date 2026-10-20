"""Lexicon loader and alias matching (spec 02). The only domain-specific data lives in lexicon.json."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any


DEFAULT_PATH = Path(__file__).parent / "domains" / "haematology" / "lexicon.json"
# Document sections a case is made of; a lexicon may define its own (any domain), these are the defaults.
DEFAULT_SECTIONS = [
    {"id": "clinical", "title": "Clinical summary"}, {"id": "morphology", "title": "Morphology"},
    {"id": "flow_cytometry", "title": "Flow cytometry"}, {"id": "cytogenetics", "title": "Cytogenetics"}, {"id": "molecular", "title": "Molecular"},
]


@dataclass(frozen=True)
class Span:
    start: int
    end: int
    text: str


@dataclass(frozen=True)
class EntityMention:
    entity: str      # parent id (e.g. MZL)
    subtype: str | None  # e.g. SMZL, WM
    start: int
    end: int
    text: str


@dataclass(frozen=True)
class MarkerToken:
    finding_id: str
    start: int
    end: int
    text: str
    alias: str


def _alias_regex(alias: str) -> re.Pattern:
    """Flexible separators inside an alias; word-bounded by lookarounds.

    Spaces and hyphens inside the alias become optional [\\s-]; `::` in fusion names accepts ::, / or -.
    Short all-caps aliases are matched case-sensitively (so the unit `fL` does not match entity FL).
    """
    parts = re.split(r"(::|[\s\-]+)", alias)
    out = []
    for p in parts:
        if p == "::":
            out.append(r"(?:::|/|-|\s)")
        elif re.fullmatch(r"[\s\-]+", p):
            out.append(r"[\s\-]?")
        elif p:
            out.append(re.escape(p))
    body = "".join(out)
    case_sensitive = len(alias) <= 5 and alias == alias.upper() and any(c.isalpha() for c in alias)
    flags = 0 if case_sensitive else re.IGNORECASE
    return re.compile(r"(?<![A-Za-z0-9])" + body + r"(?![A-Za-z0-9])", flags)


class Lexicon:
    def __init__(self, data: dict[str, Any], path: Path | None = None):
        self.data = data
        self.path = path
        self.version: str = data["version"]
        self.findings: dict[str, dict] = {f["id"]: f for f in data["findings"]}
        self.entities: dict[str, dict] = {e["id"]: e for e in data["entities"]}
        self.discriminators: dict[str, dict[str, str]] = data["discriminators"]
        self.linked: dict[str, list[str]] = data["linked"]
        self.confusion: dict[str, list[str]] = data["confusion"]
        self.phrases: dict[str, list[str]] = data["phrases"]
        self.polarity: dict[str, list[str]] = data["polarity"]
        self.cue_templates: dict[str, str] = data.get("cue_templates", {})
        self.sections: list[dict] = data.get("sections") or list(DEFAULT_SECTIONS)
        self.domain: str = data.get("domain") or "haematology"
        self._alias_patterns: list[tuple[str, str, re.Pattern]] = []
        self._alias_to_finding: dict[str, str] = {}
        for f in data["findings"]:
            for a in f["aliases"]:
                self._alias_patterns.append((f["id"], a, _alias_regex(a)))
                self._alias_to_finding[a.lower()] = f["id"]
        self._phrase_patterns: list[tuple[str, str, str, re.Pattern]] = []
        for f in data["findings"]:
            for pol, key in (("pos", "pos_phrases"), ("neg", "neg_phrases")):
                for ph in f.get(key, []):
                    self._phrase_patterns.append((f["id"], pol, ph, _alias_regex(ph)))
        self._entity_patterns: list[tuple[str, str | None, str, re.Pattern]] = []
        for e in data["entities"]:
            parent = e.get("parent")
            eid = parent or e["id"]
            sub = e["id"] if parent else None
            for a in e["aliases"]:
                self._entity_patterns.append((eid, sub, a, _alias_regex(a)))
        self._phrase_res: dict[str, list[re.Pattern]] = {}
        for k, lst in self.phrases.items():
            self._phrase_res[k] = [_phrase_regex(p) for p in lst]

    # ---- lookups
    def finding(self, fid: str) -> dict:
        return self.findings[fid]

    def display(self, fid: str) -> str:
        return self.findings[fid]["display"] if fid in self.findings else fid

    def aliases(self, fid: str) -> list[str]:
        return list(self.findings[fid]["aliases"])

    def finding_for_alias(self, alias: str) -> str | None:
        return self._alias_to_finding.get(alias.lower())

    def expected(self, fid: str, entity: str) -> str | None:
        return self.discriminators.get(fid, {}).get(entity)

    def entity_display(self, eid: str) -> str:
        return self.entities[eid]["display"] if eid in self.entities else eid

    def in_scope_entities(self) -> list[str]:
        return [e["id"] for e in self.data["entities"] if e["in_scope"] and not e.get("parent")]

    def discriminating_findings(self, entity: str) -> dict[str, str]:
        """Findings with a definite pos/neg expectation for the entity."""
        return {fid: col[entity] for fid, col in self.discriminators.items()
                if col.get(entity) in ("pos", "neg")}

    # ---- matching
    def marker_tokens(self, text: str) -> list[MarkerToken]:
        """All alias occurrences, longest-first, non-overlapping, sorted by start."""
        hits: list[tuple[int, int, str, str]] = []
        for fid, alias, pat in self._alias_patterns:
            for m in pat.finditer(text):
                hits.append((m.start(), m.end(), fid, alias))
        return [MarkerToken(fid, s, e, text[s:e], alias) for s, e, fid, alias in _resolve_overlaps(hits)]

    def phrase_matches(self, text: str) -> list[tuple[str, str, int, int, str]]:
        """(finding_id, polarity, start, end, phrase) for pos/neg phrases, longest-first non-overlapping."""
        hits: list[tuple[int, int, str, str]] = []
        for fid, pol, ph, pat in self._phrase_patterns:
            for m in pat.finditer(text):
                hits.append((m.start(), m.end(), fid, f"{pol}\x00{ph}"))
        out = []
        for s, e, fid, tag in _resolve_overlaps(hits):
            pol, ph = tag.split("\x00", 1)
            out.append((fid, pol, s, e, ph))
        return out

    def mentions_marker(self, text: str, fid: str) -> list[Span]:
        out = []
        for f, alias, pat in self._alias_patterns:
            if f != fid:
                continue
            for m in pat.finditer(text):
                out.append(Span(m.start(), m.end(), m.group(0)))
        return sorted(set(out), key=lambda s: s.start)

    def find_entities(self, text: str) -> list[EntityMention]:
        hits: list[tuple[int, int, str, str]] = []
        for eid, sub, alias, pat in self._entity_patterns:
            for m in pat.finditer(text):
                hits.append((m.start(), m.end(), eid, sub or ""))
        return [EntityMention(eid, sub or None, s, e, text[s:e]) for s, e, eid, sub in _resolve_overlaps(hits)]

    def normalise_entity_full(self, text: str) -> tuple[str | None, str | None]:
        ms = self.find_entities(text)
        if not ms:
            return None, None
        best = max(ms, key=lambda m: m.end - m.start)
        return best.entity, best.subtype

    def normalise_entity(self, text: str) -> str | None:
        return self.normalise_entity_full(text)[0]

    def has_phrase(self, kind: str, text: str) -> bool:
        return self.first_phrase(kind, text) is not None

    def first_phrase(self, kind: str, text: str) -> tuple[int, int] | None:
        best = None
        for pat in self._phrase_res.get(kind, []):
            m = pat.search(text)
            if m and (best is None or m.start() < best[0]):
                best = (m.start(), m.end())
        return best

    def wrong_cues(self, entity: str) -> list[str]:
        return list(self.confusion.get(entity, []))

    def answer_entities(self) -> list[str]:
        """Every entity id that can be an answer (in-scope parents plus answer-only ones), in file order."""
        return [e["id"] for e in self.data["entities"] if not e.get("parent")]

    def score_entity(self, found: dict[str, str], entity: str) -> tuple[int, int]:
        """(mismatches, -matches) of a finding map against the entity's definite discriminator cells."""
        mism = matches = 0
        for fid, pol in found.items():
            exp = self.discriminators.get(fid, {}).get(entity)
            if exp in ("pos", "neg"):
                if exp == pol:
                    matches += 1
                else:
                    mism += 1
        return (mism, -matches)

    def nearest_entity(self, found: dict[str, str], candidates: list[str] | None = None) -> str:
        """Entity whose definite expectations the findings fit best; ties keep file order."""
        cands = candidates or [e for e in self.answer_entities() if e in {c for col in self.discriminators.values() for c in col}]
        best = None
        for ent in cands:
            sc = self.score_entity(found, ent)
            if best is None or sc < best[0]:
                best = (sc, ent)
        return best[1] if best else "UNRESOLVED"

    def perturbation_catalogue(self) -> dict:
        """Domain-authored decisive and anchor-loss rows, if the lexicon has them (see spec 05)."""
        return self.data.get("perturbations") or {}

    def sha256(self) -> str:
        from .textutil import sha256_file
        return sha256_file(self.path) if self.path else ""


def _phrase_regex(p: str) -> re.Pattern:
    if p.strip() in ("?", "→", "=>", "->", "%"):
        return re.compile(re.escape(p))
    if p.startswith(" ") or p.endswith(" "):
        # explicit spacing from the phrase list (e.g. " so ", "if ")
        return re.compile(re.escape(p), re.IGNORECASE)
    if p.endswith(":"):
        return re.compile(r"(?<![A-Za-z0-9])" + re.escape(p), re.IGNORECASE)
    body = re.escape(p).replace(r"\ ", r"\s+")
    return re.compile(r"(?<![A-Za-z0-9])" + body + r"(?![A-Za-z0-9])", re.IGNORECASE)


def _resolve_overlaps(hits: list[tuple[int, int, str, str]]) -> list[tuple[int, int, str, str]]:
    hits.sort(key=lambda h: (h[0], -(h[1] - h[0])))
    out: list[tuple[int, int, str, str]] = []
    last_end = -1
    for h in hits:
        if h[0] < last_end:
            # overlapping: keep the longer earlier one unless this one is strictly longer and starts at same place
            if out and h[0] == out[-1][0] and (h[1] - h[0]) > (out[-1][1] - out[-1][0]):
                out[-1] = h
                last_end = h[1]
            continue
        out.append(h)
        last_end = h[1]
    return out


@lru_cache(maxsize=8)
def _load_cached(path_str: str) -> Lexicon:
    path = Path(path_str)
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    _validate_structure(data)
    return Lexicon(data, path)


def load(path: str | Path | None = None) -> Lexicon:
    return _load_cached(str(Path(path) if path else DEFAULT_PATH))


def _validate_structure(data: dict) -> None:
    for key in ("version", "entities", "findings", "discriminators", "linked", "confusion", "phrases", "polarity"):
        if key not in data:
            raise ValueError(f"lexicon missing {key!r}")
    ids = [f["id"] for f in data["findings"]]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate finding ids")
    seen: dict[str, str] = {}
    for f in data["findings"]:
        for a in f["aliases"] + f.get("pos_phrases", []) + f.get("neg_phrases", []):
            k = a.lower()
            if k in seen and seen[k] != f["id"]:
                raise ValueError(f"alias {a!r} shared by {seen[k]} and {f['id']}")
            seen[k] = f["id"]
    for fid in data["discriminators"]:
        if fid not in ids:
            raise ValueError(f"discriminator for unknown finding {fid}")
    for e in data["entities"]:
        if not e["aliases"]:
            raise ValueError(f"entity {e['id']} has no aliases")
