"""Ledger I/O: JSON round trip, rendering a ledger case for a model, and parsing a model's structured output.

A rendered case is a markdown document of fact tables with ids that `importers.enable_md.parse_facts` reads back,
so the same text can be a prompt (path A: traceaudit calls the model) or an export (path B: an external engine
runs it). The output contract (prompts/ledger-v1.json) is one JSON object: a decision, a report whose segments
cite fact ids, a differential with criteria, and the stated discriminators. `parse_output` is tolerant: it finds
the JSON in prose or fences, repairs trailing commas, accepts the ENABLE engine's key names, and falls back to a
text reading when a model ignores the contract, recording what it had to do in warnings. Standard library only.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable

from . import ledger as L
from .grounding import ParsedAnswer
from .ledger import Ablation, Criterion, DifferentialEntry, Fact, LedgerCase, LedgerTrace, Rationale, Report, Section, Segment
from .lexicon import Lexicon
from .schema import read_jsonl, write_jsonl

REFERENCE_HEADING = "Reference criteria"
DECISION_STATUSES = ("definitive", "provisional", "indeterminate")
CONFIDENCES = ("high", "moderate", "low")
VERDICTS = ("favoured", "possible", "unlikely", "excluded")
CRITERION_STATUSES = ("met", "not_met", "not_assessable")
CONTRACT_BREAKING = ("NO_JSON", "MISSING_DECISION", "DECISION_NOT_CANDIDATE", "UNKNOWN_IDS", "NO_REPORT")


# ----------------------------------------------------------------------------- JSON round trip

def case_to_dict(case: LedgerCase) -> dict:
    return {"case_id": case.case_id, "truth": case.truth, "candidates": list(case.candidates),
            "facts": [{"id": f.id, "source": f.source, "section": f.section, "field": f.field, "value": f.value,
                       "evidence": f.evidence, "candidate": f.candidate} for f in case.facts],
            "allowed_ids": sorted(case.allowed_ids), "meta": dict(case.meta)}


def case_from_dict(d: dict) -> LedgerCase:
    facts = [Fact(f["id"], f.get("source", "patient"), f.get("section", ""), f.get("field", ""), str(f.get("value", "")),
                  f.get("evidence", ""), f.get("candidate")) for f in d.get("facts", [])]
    return LedgerCase(d.get("case_id", "case"), d.get("truth"), list(d.get("candidates", [])), facts,
                      set(d.get("allowed_ids", [])) | {f.id for f in facts}, dict(d.get("meta", {})))


def trace_to_dict(trace: LedgerTrace) -> dict:
    rep = trace.report
    out: dict = {"thinking": trace.thinking,
                 "report": {"decision": rep.decision, "delivered_decision": rep.delivered_decision, "contract_valid": rep.contract_valid,
                            "failure_kind": rep.failure_kind, "dropped_segments": list(rep.dropped_segments),
                            "sections": [{"title": s.title, "segments": [{"text": g.text, "citation_ids": list(g.citation_ids)} for g in s.segments]}
                                         for s in rep.sections]},
                 "rationale": None, "ablation": None, "meta": dict(trace.meta)}
    r = trace.rationale
    if r is not None:
        out["rationale"] = {"decision": r.decision, "confidence": r.confidence, "key_findings": list(r.key_findings),
                            "differential": [{"diagnosis": d.diagnosis, "verdict": d.verdict, "supporting": list(d.supporting),
                                              "contradicting": list(d.contradicting), "rationale": d.rationale,
                                              "criteria": [{"criterion": c.criterion, "status": c.status, "ids": list(c.ids)} for c in d.criteria]}
                                             for d in r.differential],
                            "discriminators": list(r.discriminators), "unresolved": list(r.unresolved), "would_change": list(r.would_change),
                            "thinking": r.thinking}
    a = trace.ablation
    if a is not None:
        out["ablation"] = {"removed_ids": list(a.removed_ids), "decision_before": a.decision_before, "decision_after": a.decision_after, "changed": a.changed}
    return out


def trace_from_dict(d: dict) -> LedgerTrace:
    rep = d.get("report") or {}
    report = Report(rep.get("decision"), [Section(sec.get("title", ""), [Segment(sg.get("text", ""), list(sg.get("citation_ids", [])))
                                                                       for sg in sec.get("segments", [])]) for sec in rep.get("sections", [])],
                    rep.get("delivered_decision"), rep.get("contract_valid"), rep.get("failure_kind"), list(rep.get("dropped_segments", [])))
    rationale = None
    if d.get("rationale"):
        r = d["rationale"]
        rationale = Rationale(r.get("decision"), r.get("confidence"), list(r.get("key_findings", [])),
                              [DifferentialEntry(x["diagnosis"], x.get("verdict", "unknown"), list(x.get("supporting", [])), list(x.get("contradicting", [])),
                                                 x.get("rationale", ""), [Criterion(c["criterion"], c.get("status", "not_assessable"), list(c.get("ids", [])))
                                                                          for c in x.get("criteria", [])])
                               for x in r.get("differential", [])],
                              list(r.get("discriminators", [])), list(r.get("unresolved", [])), list(r.get("would_change", [])), r.get("thinking", ""))
    ablation = None
    if d.get("ablation"):
        a = d["ablation"]
        ablation = Ablation(list(a.get("removed_ids", [])), a.get("decision_before"), a.get("decision_after"), a.get("changed"))
    return LedgerTrace(d.get("thinking", ""), report, rationale, ablation, dict(d.get("meta", {})))


def load_cases(path: str | Path) -> list[LedgerCase]:
    return [case_from_dict(d) for d in read_jsonl(path)]


def write_cases(path: str | Path, cases: Iterable[LedgerCase]) -> int:
    return write_jsonl(path, (case_to_dict(c) for c in cases))


def fact_fingerprint(case: LedgerCase) -> str:
    """sha256 over the ordered (id, field, value) triples: identifies a case variant regardless of evidence wording."""
    h = hashlib.sha256()
    for f in case.facts:
        h.update(f"{f.id}\t{f.field}\t{f.value}\n".encode())
    return h.hexdigest()


# ----------------------------------------------------------------------------- rendering

def _cell(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text if text is not None else "")).replace("|", "/").strip()


def _section_title(section: str) -> str:
    return (section or "other").replace("_", " ")


def render_case(case: LedgerCase, evidence: bool = True) -> str:
    """Markdown fact tables with ids, as the model sees them. Carries no case id, truth, variant or edit rationale.

    Round-trips through `importers.enable_md.parse_markdown`: patient sections by `section`, context sections whose
    heading contains "context", and one reference block per candidate under a "Reference criteria" heading.
    """
    lines: list[str] = []
    if case.candidates:
        lines.append("Candidate answers: " + "; ".join(case.candidates))
        lines.append("")
    lines.append("## 1. Available information")
    lines.append("")
    groups: dict[tuple[str, str], list[Fact]] = {}
    for f in case.facts:
        if f.source == "who":
            continue
        groups.setdefault((f.source, f.section), []).append(f)
    for (source, section), facts in groups.items():
        title = _section_title(section)
        if source == "context" and "context" not in title.lower():
            title += " context"
        lines.append(f"### {title} ({len(facts)} facts)")
        if evidence:
            lines.append("| ids | field | value | evidence snippet |")
            lines.append("| --- | --- | --- | --- |")
            lines += [f"| {f.id} | {_cell(f.field)} | {_cell(f.value)} | {_cell(f.evidence)} |" for f in facts]
        else:
            lines.append("| ids | field | value |")
            lines.append("| --- | --- | --- |")
            lines += [f"| {f.id} | {_cell(f.field)} | {_cell(f.value)} |" for f in facts]
        lines.append("")
    refs = [f for f in case.facts if f.source == "who"]
    if refs:
        by_cand: dict[str, list[Fact]] = {}
        for f in refs:
            by_cand.setdefault(f.candidate or f.section or "reference", []).append(f)
        order = [c for c in case.candidates if c in by_cand] + [c for c in by_cand if c not in case.candidates]
        lines.append(f"### {REFERENCE_HEADING} ({len(refs)} facts across {len(by_cand)} candidates)")
        for cand in order:
            lines.append(f"**{cand}**")
            lines.append("| ids | field | value |")
            lines.append("| --- | --- | --- |")
            lines += [f"| {f.id} | {_cell(f.field)} | {_cell(f.value)} |" for f in by_cand[cand]]
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


# ----------------------------------------------------------------------------- decisions and hedging

def _word_re(s: str) -> re.Pattern:
    return re.compile(r"(?<![A-Za-z0-9])" + re.escape(s) + r"(?![A-Za-z0-9])", re.IGNORECASE)


def candidates_in(text: str, case: LedgerCase, base_lexicon: Lexicon | None = None) -> list[str]:
    """Candidates named in the text, in order of first appearance (exact name, slash parts, or lexicon entity aliases)."""
    hits: list[tuple[int, str]] = []
    for c in case.candidates:
        best = None
        for a in [c] + L._candidate_aliases(c):
            m = _word_re(a).search(text)
            if m and (best is None or m.start() < best):
                best = m.start()
        if best is not None:
            hits.append((best, c))
    if base_lexicon is not None:
        named = {c for _, c in hits}
        by_display = {}
        for eid, e in base_lexicon.entities.items():
            for key in (eid, e.get("display", "")):
                by_display[str(key).lower()] = eid
        for m in base_lexicon.find_entities(text):
            for c in case.candidates:
                if c in named:
                    continue
                if by_display.get(c.lower()) == m.entity or base_lexicon.entity_display(m.entity).lower() == c.lower():
                    hits.append((m.start, c))
                    named.add(c)
    hits.sort()
    out: list[str] = []
    for _, c in hits:
        if c not in out:
            out.append(c)
    return out


def normalise_decision(text: str | None, case: LedgerCase, base_lexicon: Lexicon | None = None) -> tuple[str, list[str], bool]:
    """(entity, candidates named, hedged by the text). Unknown non-empty text gives OTHER; empty or 'indeterminate' gives UNRESOLVED."""
    t = (text or "").strip()
    if not t:
        return "UNRESOLVED", [], True
    for c in case.candidates:
        if t.lower() == c.lower():
            return c, [c], False
    named = candidates_in(t, case, base_lexicon)
    indeterminate = bool(re.search(r"\b(indeterminate|undetermined|uncertain|unresolved|cannot be determined)\b", t, re.I))
    if len(named) >= 2:
        return named[0], named, True
    if len(named) == 1:
        return named[0], named, indeterminate
    return ("UNRESOLVED", [], True) if indeterminate else ("OTHER", [], False)


def ledger_answer(trace: LedgerTrace, case: LedgerCase, base_lexicon: Lexicon | None = None) -> tuple[ParsedAnswer, dict]:
    """The structured answer as a ParsedAnswer (entity, hedged, entities named) plus the hedge signals behind it.

    Signals, each recorded so a sensitivity analysis can drop any one [PRE-REG]:
      status           decision_status is provisional or indeterminate (path A only)
      confidence_low   confidence == low (output contract or rationale)
      multi_decision   the decision text names two or more candidates, or is indeterminate
      favoured_count   a rationale is present and the number of favoured entries is not one
    """
    rep = trace.report
    raw = rep.delivered_decision or rep.decision
    entity, named, hedged_text = normalise_decision(raw, case, base_lexicon)
    status = (trace.meta or {}).get("decision_status")
    conf = (trace.meta or {}).get("confidence") or (trace.rationale.confidence if trace.rationale else None)
    fav = None
    if trace.rationale is not None and trace.rationale.differential:
        fav = sum(1 for d in trace.rationale.differential if d.verdict == "favoured")
    signals = {"status": status in ("provisional", "indeterminate"), "confidence_low": (conf or "").lower() == "low",
               "multi_decision": hedged_text, "favoured_count": fav is not None and fav != 1}
    pa = ParsedAnswer(entity=entity, entity_raw=raw, subtype=None, hedged=any(signals.values()), entities_named=named, diagnosis_line=raw)
    return pa, {**signals, "confidence": conf, "decision_status": status, "favoured": fav}


# ----------------------------------------------------------------------------- parsing model output

def _json_candidates(text: str) -> list[str]:
    """Strings that may hold the output object: fenced blocks (last first), the whole text, balanced {...} spans from the end."""
    out: list[str] = []
    for m in reversed(list(re.finditer(r"```(?:json|JSON)?\s*\n(.*?)```", text, re.S))):
        out.append(m.group(1))
    out.append(text.strip())
    # balanced top-level objects, string-aware, scanned from the end
    depth = 0
    end = None
    in_str = False
    for i in range(len(text) - 1, -1, -1):
        ch = text[i]
        if in_str:
            if ch == '"' and not (i > 0 and text[i - 1] == "\\"):
                in_str = False
            continue
        if ch == '"':
            in_str = True
            continue
        if ch == "}":
            if depth == 0:
                end = i
            depth += 1
        elif ch == "{":
            depth -= 1
            if depth == 0 and end is not None:
                out.append(text[i:end + 1])
                end = None
                if len(out) > 6:
                    break
    return out


def _loads(s: str) -> tuple[dict | None, bool]:
    """Parse a JSON object; a second attempt removes trailing commas. Returns (obj, repaired)."""
    try:
        v = json.loads(s)
        return (v if isinstance(v, dict) else None), False
    except json.JSONDecodeError:
        pass
    fixed = re.sub(r",\s*([}\]])", r"\1", s)
    if fixed != s:
        try:
            v = json.loads(fixed)
            return (v if isinstance(v, dict) else None), True
        except json.JSONDecodeError:
            return None, False
    return None, False


def find_json(answer: str, thinking: str = "") -> tuple[dict | None, list[str]]:
    warnings: list[str] = []
    for cand in _json_candidates(answer or ""):
        obj, repaired = _loads(cand)
        if obj is not None:
            if repaired:
                warnings.append("JSON_REPAIRED")
            return obj, warnings
    if thinking:
        tail = thinking[-20000:]
        for cand in _json_candidates(tail):
            obj, repaired = _loads(cand)
            if obj is not None and ("decision" in obj or "predicted_diagnosis" in obj or "report" in obj or "sections" in obj):
                warnings.append("JSON_IN_REASONING")
                if repaired:
                    warnings.append("JSON_REPAIRED")
                return obj, warnings
    warnings.append("NO_JSON")
    return None, warnings


def _ids(v: Any) -> list[str]:
    if v is None:
        return []
    if isinstance(v, str):
        return [i for i in re.split(r"[,\s]+", v.replace("[", " ").replace("]", " ")) if L.ID_RE.fullmatch(i.strip("`"))]
    if isinstance(v, list):
        out: list[str] = []
        for x in v:
            out += _ids(x) if isinstance(x, (str, list)) else []
        return out
    return []


def _segments(sec: Any, warnings: list[str]) -> list[Segment]:
    segs = sec.get("segments") if isinstance(sec, dict) else None
    if segs is None and isinstance(sec, dict) and isinstance(sec.get("text"), str):
        segs = [sec]
    out: list[Segment] = []
    for sg in segs or []:
        if isinstance(sg, str):
            warnings.append("CITATIONS_INLINE")
            out.append(Segment(L.ID_RE.sub("", sg).replace("[]", "").strip(), sorted(set(L.ID_RE.findall(sg)))))
        elif isinstance(sg, dict):
            text = str(sg.get("text", ""))
            ids = _ids(sg.get("citation_ids", sg.get("citations", sg.get("ids"))))
            if not ids and L.ID_RE.search(text):
                warnings.append("CITATIONS_INLINE")
                ids = sorted(set(L.ID_RE.findall(text)))
            out.append(Segment(text, ids))
    return out


def parse_output(answer: str, case: LedgerCase, thinking: str = "", base_lexicon: Lexicon | None = None) -> tuple[LedgerTrace, list[str]]:
    """Read a model's reply against the ledger-v1 contract. Always returns a trace; warnings say what was tolerated.

    `trace.report.contract_valid` is False when a contract-breaking warning occurred (NO_JSON, MISSING_DECISION,
    DECISION_NOT_CANDIDATE, UNKNOWN_IDS, NO_REPORT); `trace.meta["parse_mode"]` is "contract" or "text_fallback".
    """
    obj, warnings = find_json(answer, thinking)
    allowed = set(case.allowed_ids) | {f.id for f in case.facts}
    meta: dict = {"parse_mode": "contract"}
    if obj is None:
        decision = None
        m = re.search(r"^\s*(?:final\s+)?(?:decision|diagnosis|integrated diagnosis|answer)\s*[:\-]\s*(.+?)\s*$", answer or "", re.I | re.M)
        if m:
            decision = m.group(1).strip().rstrip(".")
        else:
            named = candidates_in(answer or "", case, base_lexicon)
            decision = named[0] if named else None
        if decision is None:
            warnings.append("MISSING_DECISION")
        ids = sorted(set(L.ID_RE.findall(answer or "")))
        report = Report(decision, [Section("Answer", [Segment((answer or "").strip(), ids)])] if (answer or "").strip() else [], decision,
                        False, "NO_JSON", [])
        meta["parse_mode"] = "text_fallback"
        cm = re.search(r"^\s*confidence\s*[:\-]\s*(high|moderate|low)\b", answer or "", re.I | re.M)
        sm = re.search(r"^\s*(?:decision[_ ]status|status)\s*[:\-]\s*(definitive|provisional|indeterminate)\b", answer or "", re.I | re.M)
        meta.update({"confidence": cm.group(1).lower() if cm else None, "decision_status": sm.group(1).lower() if sm else None, "unknown_ids": []})
        return LedgerTrace(thinking, report, None, None, meta), warnings
    decision = obj.get("decision", obj.get("predicted_diagnosis", obj.get("diagnosis")))
    decision = str(decision).strip() if decision not in (None, "") else None
    if decision is None:
        warnings.append("MISSING_DECISION")
    elif decision.lower() != "indeterminate" and not candidates_in(decision, case, base_lexicon) and decision not in case.candidates:
        warnings.append("DECISION_NOT_CANDIDATE")
    status = obj.get("decision_status")
    if status is not None and status not in DECISION_STATUSES:
        warnings.append("BAD_STATUS")
        status = None
    conf = obj.get("confidence")
    if conf is not None and str(conf).lower() not in CONFIDENCES:
        warnings.append("BAD_CONFIDENCE")
        conf = None
    rep = obj.get("report") if isinstance(obj.get("report"), dict) else obj
    sections: list[Section] = []
    for sec in rep.get("sections") or []:
        if isinstance(sec, dict):
            sections.append(Section(str(sec.get("title", "")), _segments(sec, warnings)))
    if not sections:
        warnings.append("NO_REPORT")
    rationale = None
    diff_src = obj.get("differential")
    if isinstance(diff_src, list) and diff_src:
        entries = []
        for d in diff_src:
            if not isinstance(d, dict):
                continue
            verdict = str(d.get("verdict", "unknown")).lower()
            if verdict not in VERDICTS:
                warnings.append("BAD_VERDICT")
            crit = []
            for c in d.get("criteria") or []:
                if isinstance(c, dict):
                    st = str(c.get("status", "not_assessable")).lower()
                    if st not in CRITERION_STATUSES:
                        warnings.append("BAD_CRITERION_STATUS")
                        st = "not_assessable"
                    crit.append(Criterion(str(c.get("criterion", "")), st, _ids(c.get("ids"))))
            entries.append(DifferentialEntry(str(d.get("diagnosis", "")), verdict, _ids(d.get("supporting")), _ids(d.get("contradicting")),
                                             str(d.get("rationale", "")), crit))
        discs = [{"text": str(x.get("text", "")), "ids": _ids(x.get("ids"))} if isinstance(x, dict) else {"text": str(x), "ids": _ids(str(x))}
                 for x in obj.get("discriminators") or []]
        rationale = Rationale(decision, str(conf).lower() if conf else None, list(obj.get("key_findings") or []), entries, discs,
                              [str(x) for x in obj.get("unresolved") or []], [str(x) for x in obj.get("would_change") or []], "")
    elif "differential" not in obj:
        warnings.append("NO_RATIONALE")
    cited = {i for s in sections for g in s.segments for i in g.citation_ids}
    if rationale is not None:
        for d in rationale.differential:
            cited |= set(d.supporting) | set(d.contradicting) | {i for c in d.criteria for i in c.ids}
        cited |= {i for x in rationale.discriminators for i in x["ids"]}
    unknown = sorted(i for i in cited if i not in allowed)
    if unknown:
        warnings.append("UNKNOWN_IDS")
    ablation = None
    if isinstance(obj.get("ablation"), dict):
        a = obj["ablation"]
        ablation = Ablation(_ids(a.get("removed_ids")), a.get("decision_before"), a.get("decision_after"), a.get("changed"))
    breaking = [w for w in warnings if w in CONTRACT_BREAKING]
    delivered = obj.get("delivered_decision") or decision
    report = Report(decision, sections, str(delivered).strip() if delivered else None,
                    obj.get("contract_valid") if isinstance(obj.get("contract_valid"), bool) else not breaking,
                    obj.get("failure_kind") or (breaking[0] if breaking else None), list(obj.get("dropped_segments") or []))
    meta.update({"decision_status": status, "confidence": str(conf).lower() if conf else None, "unknown_ids": unknown})
    return LedgerTrace(thinking, report, rationale, ablation, meta), warnings
