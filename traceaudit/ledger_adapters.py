"""Adapters from the free-text path (specs 03-04) to the fact ledger (spec 18).

The text path turns documents into polarised assertions (`extract.finding_spans`) and a reasoning trace into typed
claims (`segment.segment`). Here every assertion found in a document becomes a patient `Fact` carrying its evidence
span, an authority cue appended to a document becomes a context fact, and every factual claim becomes a report
`Segment` that cites the facts it restates. `ledger.audit` then runs the same checks on free text as on a structured
artefact, so the service and the viewer have one result shape. Standard library only.
"""
from __future__ import annotations

import re

from . import extract, grounding
from .ledger import Fact, LedgerCase, LedgerTrace, Report, Section, Segment, value_polarity
from .lexicon import Lexicon
from .schema import Case, Claim, Trace

CUE_FIELD = "referrer_working_diagnosis"
CLAIMS_SECTION = "Factual claims"


def polarity_word(lx: Lexicon, polarity: str) -> str:
    """The lexicon's own display word for a polarity: the first alphabetic suffix the ledger reads back as that
    polarity ("positive" -> "Positive"), else Positive/Negative."""
    key = "pos_suffix" if polarity == "pos" else "neg_suffix"
    for w in lx.polarity.get(key, []):
        if w.isalpha() and value_polarity(w) == polarity:
            return w.capitalize()
    return "Positive" if polarity == "pos" else "Negative"


def find_cues(case: Case, lx: Lexicon) -> list[dict]:
    """Authority cues (schema.Cue) rendered from the lexicon's cue templates and appended to a document, in document
    order: [{report, start, end, text, entity}]. `entity` is the lexicon id when the cue's wording resolves, else the raw text."""
    patterns = []
    for tmpl in lx.cue_templates.values():
        if "{entity}" not in tmpl:
            continue
        patterns.append(re.compile(re.escape(tmpl).replace(re.escape("{entity}"), "(.+?)"), re.IGNORECASE))
    out: list[dict] = []
    for key, _title in case.section_list():
        body = case.reports.get(key) or ""
        for pat in patterns:
            for m in pat.finditer(body):
                raw = m.group(1).strip()
                out.append({"report": key, "start": m.start(), "end": m.end(), "text": m.group(0), "entity": lx.normalise_entity(raw) or raw})
    return out


def case_to_ledger(case: Case, lx: Lexicon, truth_overrides: bool = False) -> LedgerCase:
    """One patient fact per polarised assertion in the documents (ids `p_1..` in document order), one context fact per
    authority cue (`c_1..`). `meta["spans"]` maps each fact id to `{report, start, end}` offsets into `case.reports`.

    With `truth_overrides`, a supplied truth table is the oracle: a fact whose document polarity differs from the
    table takes the table's value (the document's own reading stays in `meta["stated"]`), and a truth entry no document
    states becomes a fact without evidence. Without it the documents speak for themselves."""
    order = [k for k, _ in case.section_list()]
    rows: list[tuple[int, int, str, dict]] = []
    for fid, spans in extract.finding_spans(case, lx).items():
        for sp in spans:
            start = min(sp["start"], sp["cue_start"])
            rows.append((order.index(sp["report"]) if sp["report"] in order else len(order), start, fid, sp))
    rows.sort(key=lambda r: (r[0], r[1], r[2]))
    truth = dict(case.truth or {}) if truth_overrides else {}
    facts: list[Fact] = []
    spans_meta: dict[str, dict] = {}
    stated_meta: dict[str, str] = {}
    seen_fields: set[str] = set()
    for i, (_, start, fid, sp) in enumerate(rows, 1):
        pid = f"p_{i}"
        end = max(sp["end"], sp["cue_end"])
        pol = truth.get(fid, sp["polarity"])
        facts.append(Fact(pid, "patient", sp["report"], fid, polarity_word(lx, pol), case.reports[sp["report"]][start:end]))
        spans_meta[pid] = {"report": sp["report"], "start": start, "end": end}
        if pol != sp["polarity"]:
            stated_meta[pid] = polarity_word(lx, sp["polarity"])
        seen_fields.add(fid)
    for fid, pol in truth.items():
        if fid in seen_fields or pol not in ("pos", "neg"):
            continue
        facts.append(Fact(f"p_{len(facts) + 1}", "patient", "truth", fid, polarity_word(lx, pol), ""))
    for j, cue in enumerate(find_cues(case, lx), 1):
        cid = f"c_{j}"
        facts.append(Fact(cid, "context", cue["report"], CUE_FIELD, lx.entity_display(cue["entity"]), cue["text"]))
        spans_meta[cid] = {"report": cue["report"], "start": cue["start"], "end": cue["end"]}
    meta = {"documents": order, "spans": spans_meta, "lexicon_fields": True}
    if stated_meta:
        meta["stated"] = stated_meta
    truth_entity = case.entity if case.entity in lx.entities else None
    return LedgerCase(case.case_id, truth_entity, lx.answer_entities(), facts, {f.id for f in facts}, meta)


def trace_to_ledger(trace: Trace, claims: list[Claim], lx: Lexicon, case_ledger: LedgerCase) -> LedgerTrace:
    """Thinking is the reasoning; the report is one section of factual claims, each citing the fact for every finding
    it asserts: the fact with the same polarity when the documents state the finding more than once, else the first
    fact for that field (so a contradicted claim cites the fact it contradicts). A finding no document states is left
    uncited and surfaces as an uncited assertion. The decision is the parsed answer entity."""
    by_field: dict[str, list[Fact]] = {}
    for f in case_ledger.facts:
        if f.source == "patient":
            by_field.setdefault(f.field, []).append(f)
    segments: list[Segment] = []
    for c in claims:
        if c.type != "factual":
            continue
        ids: list[str] = []
        for a in c.assertions:
            if not a.polarity:
                continue
            cands = by_field.get(a.finding_id, [])
            same = [f for f in cands if f.polarity == a.polarity]
            pick = (same or cands)[:1]
            for f in pick:
                if f.id not in ids:
                    ids.append(f.id)
        segments.append(Segment(c.text, ids))
    pa = grounding.parse_answer(trace.answer, lx)
    report = Report(decision=pa.entity, sections=[Section(CLAIMS_SECTION, segments)])
    meta = {"hedged": pa.hedged, "claims": len(claims), "factual_claims": len(segments), "answer": trace.answer,
            "entity_raw": pa.entity_raw, "subtype": pa.subtype, "entities_named": pa.entities_named}
    return LedgerTrace(thinking=trace.reasoning, report=report, meta=meta)
