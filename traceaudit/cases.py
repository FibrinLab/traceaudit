"""Build cases from documents with a known answer, for any domain (researcher tooling)."""
from __future__ import annotations

from pathlib import Path

from . import extract
from . import lexicon as lex_mod
from .lexicon import Lexicon
from .schema import Case, Provenance, Review, read_jsonl


def build_case(record: dict, lx: Lexicon, approve: bool = False) -> tuple[Case, list[str]]:
    """record: {case_id, entity, documents{section id: text}, truth?, subtype?, titles?}.

    Truth is taken from the record when given, otherwise read from the documents by the extractor.
    Returns the case and a list of human-readable problems (empty when the case is clean)."""
    problems: list[str] = []
    docs = record.get("documents") or record.get("reports") or {}
    if not isinstance(docs, dict) or not docs:
        return None, ["documents must be a non-empty object of section id -> text"]  # type: ignore[return-value]
    known = {s["id"]: s.get("title") for s in lx.sections}
    titles = record.get("titles") or {}
    sections = [{"id": k, "title": titles.get(k) or known.get(k) or k.replace("_", " ").capitalize()} for k in docs]
    for k, v in docs.items():
        if not isinstance(v, str):
            problems.append(f"document {k} is not text")
    entity = record.get("entity")
    if entity not in lx.entities:
        problems.append(f"entity {entity!r} is not in the lexicon ({', '.join(lx.answer_entities())})")
    case = Case(case_id=record.get("case_id") or "CASE-000", entity=entity or "OTHER", reports={k: v or "" for k, v in docs.items()},
                truth={}, subtype=record.get("subtype"), sections=sections, provenance=Provenance(template_id="cases build"))
    if record.get("truth"):
        case.truth = {k: v for k, v in record["truth"].items()}
        try:
            found = extract.findings(case.render(), lx)
        except extract.PolarityConflict as e:
            problems.append(f"conflicting polarity in the documents: {e}")
            found = {}
        for f, v in case.truth.items():
            if f not in lx.findings:
                problems.append(f"truth names unknown finding {f}")
            elif found.get(f) != v:
                problems.append(f"truth says {f}={v} but the documents read as {found.get(f, 'absent')}; the model would be graded against text it cannot see")
        for f in found:
            if f not in case.truth:
                problems.append(f"documents assert {f}={found[f]} but it is not in the truth; add it or remove the sentence")
    else:
        try:
            case.truth = extract.findings(case.render(), lx)
        except extract.PolarityConflict as e:
            problems.append(f"conflicting polarity in the documents: {e}")
        if not case.truth:
            problems.append("no findings from the lexicon were recognised in the documents")
    for k, v in docs.items():
        if not (v or "").strip():
            case.flags.incomplete = True
            case.flags.missing_modalities.append(k)
    if approve:
        case.review = Review(reviewer_id="builder", date="", status="approved", notes="approved on build")
    return case, problems


def build_cases(src: str | Path, lx: Lexicon | None = None, approve: bool = False) -> tuple[list[Case], dict[str, list[str]]]:
    lx = lx or lex_mod.load()
    cases: list[Case] = []
    problems: dict[str, list[str]] = {}
    for i, rec in enumerate(read_jsonl(src)):
        case, probs = build_case(rec, lx, approve)
        if probs:
            problems[rec.get("case_id") or f"line {i + 1}"] = probs
        if case is not None:
            cases.append(case)
    return cases, problems


def coverage_report(cases: list[Case], lx: Lexicon) -> dict:
    """How well the case set exercises the lexicon: findings never asserted, entities with few cases."""
    asserted: dict[str, int] = {}
    per_entity: dict[str, int] = {}
    for c in cases:
        per_entity[c.entity] = per_entity.get(c.entity, 0) + 1
        for f in c.truth:
            asserted[f] = asserted.get(f, 0) + 1
    never = [f for f in lx.findings if f not in asserted]
    return {"cases": len(cases), "per_entity": per_entity, "findings_asserted": len(asserted), "findings_never_asserted": never,
            "entities_without_cases": [e for e in lx.in_scope_entities() if e not in per_entity]}
