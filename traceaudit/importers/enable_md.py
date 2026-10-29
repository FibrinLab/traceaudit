"""Importer for the ENABLE-AI reasoning-trace markdown artefact (facts tables, thinking, report JSON, rationale, ablation).

The format is the one the ENABLE engine writes per case/repeat:
  ## 1. Available information            -> fact tables per modality, WHO blocks per candidate
  ## 2. Model's own reasoning            -> fenced block with the arm A thinking
  ## 3. Delivered report                 -> fenced json block with predicted_diagnosis + sections
  ## 4. Structured rationale (arm B)     -> key findings, differential, WHO criteria, decision detail tables
  ## 5. Discriminator ablation (arm C)   -> removed facts and the decision without them
Anything missing is tolerated; the ledger then has fewer checks.
"""
from __future__ import annotations

import json
import re

from .. import ledger

_H2 = re.compile(r"^## (\d+)\.\s*(.*)$", re.M)
_H3 = re.compile(r"^### (.+?)\s*(?:\((\d+) facts?.*\))?\s*$", re.M)
_BOLD = re.compile(r"^\*\*(.+?)\*\*.*$", re.M)
_FENCE = re.compile(r"```(?:json)?\n(.*?)```", re.S)


def _split_h2(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    marks = list(_H2.finditer(text))
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        out[m.group(1)] = text[m.end():end]
    return out


def _tables(block: str) -> list[tuple[list[str], list[list[str]]]]:
    """All markdown tables in a block: (header cells, rows)."""
    tables = []
    lines = block.splitlines()
    i = 0
    while i < len(lines):
        if lines[i].startswith("|") and i + 1 < len(lines) and re.match(r"^\|\s*-", lines[i + 1]):
            header = [c.strip() for c in lines[i].strip().strip("|").split("|")]
            rows = []
            i += 2
            while i < len(lines) and lines[i].startswith("|"):
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            tables.append((header, rows))
        else:
            i += 1
    return tables


def _ids(cell: str) -> list[str]:
    return [i.strip().strip("`") for i in re.split(r"[,\s]+", cell.replace("[", " ").replace("]", " ")) if ledger.ID_RE.fullmatch(i.strip().strip("`"))]


def parse_facts(block: str) -> tuple[list[ledger.Fact], list[str]]:
    facts: list[ledger.Fact] = []
    candidates: list[str] = []
    # patient / context sections: "### <modality> (n facts)"
    sections = list(_H3.finditer(block))
    for i, m in enumerate(sections):
        name = m.group(1).strip()
        end = sections[i + 1].start() if i + 1 < len(sections) else len(block)
        body = block[m.end():end]
        if name.lower().startswith(("who", "reference")):
            # candidate blocks "**NAME**" each followed by a table (WHO blocks in ENABLE artefacts; "Reference criteria" in rendered cases)
            cands = list(_BOLD.finditer(body))
            for j, cm in enumerate(cands):
                cand = cm.group(1).strip()
                candidates.append(cand)
                cend = cands[j + 1].start() if j + 1 < len(cands) else len(body)
                for header, rows in _tables(body[cm.end():cend]):
                    for r in rows:
                        for fid in _ids(r[0]):
                            facts.append(ledger.Fact(fid, "who", cand, r[1] if len(r) > 1 else "", r[2] if len(r) > 2 else "", "", cand))
            continue
        source = "context" if "context" in name.lower() else "patient"
        section = name.lower().replace(" ", "_")
        for header, rows in _tables(body):
            for r in rows:
                for fid in _ids(r[0]):
                    facts.append(ledger.Fact(fid, source, section, r[1] if len(r) > 1 else "", r[2] if len(r) > 2 else "",
                                             r[3] if len(r) > 3 else ""))
    return facts, candidates


def parse_report(block: str) -> ledger.Report:
    decision = None
    delivered = None
    m = re.search(r"predicted_diagnosis raw:\s*\*\*(.+?)\*\*\s*·\s*delivered:\s*\*\*(.+?)\*\*", block)
    if m:
        decision, delivered = m.group(1).strip(), m.group(2).strip()
    cv = re.search(r"contract_valid:\s*(True|False)", block)
    fk = re.search(r"failure_kind:\s*`([^`]+)`", block)
    sections: list[ledger.Section] = []
    fences = _FENCE.findall(block)
    raw = None
    for f in fences:
        try:
            raw = json.loads(f)
            break
        except json.JSONDecodeError:
            continue
    if raw:
        decision = decision or raw.get("predicted_diagnosis")
        for sec in raw.get("sections", []):
            sections.append(ledger.Section(sec.get("title", ""), [ledger.Segment(s.get("text", ""), list(s.get("citation_ids", []))) for s in sec.get("segments", [])]))
    dropped = []
    dm = re.search(r"Removed by post-processing.*?\n((?:- .*\n?)+)", block)
    if dm:
        for line in dm.group(1).splitlines():
            if line.startswith("- "):
                title, _, text = line[2:].partition(": ")
                dropped.append({"section": title.strip(), "text": text.strip()})
    # the delivered (post-processed) report drops uncited segments; reflect that in the sections when we know what was dropped
    if dropped:
        for sec in sections:
            sec.segments = [s for s in sec.segments if not any(d["section"] == sec.title.rstrip(":") and d["text"] == s.text for d in dropped)]
    return ledger.Report(decision, sections, delivered, None if not cv else cv.group(1) == "True", fk.group(1) if fk else None, dropped)


def parse_rationale(block: str) -> ledger.Rationale:
    m = re.search(r"Decision:\s*\*\*(.+?)\*\*(?:\s*·\s*confidence:\s*(\w+))?", block)
    rat = ledger.Rationale(m.group(1).strip() if m else None, m.group(2) if m and m.group(2) else None)
    parts = re.split(r"^### ", block, flags=re.M)
    for part in parts:
        head, _, body = part.partition("\n")
        h = head.strip().lower()
        if h.startswith("key findings"):
            for header, rows in _tables(body):
                for r in rows:
                    if len(r) >= 3:
                        rat.key_findings.append({"modality": r[0], "description": r[1], "ids": _ids(r[2])})
        elif h.startswith("differential"):
            for header, rows in _tables(body):
                for r in rows:
                    if len(r) >= 6:
                        rat.differential.append(ledger.DifferentialEntry(r[0], r[1], _ids(r[2]), _ids(r[3]), r[5]))
        elif h.startswith(("who criteria", "reference criteria")):
            cands = list(_BOLD.finditer(body))
            for j, cm in enumerate(cands):
                cand = cm.group(1).strip()
                cend = cands[j + 1].start() if j + 1 < len(cands) else len(body)
                entry = next((d for d in rat.differential if d.diagnosis == cand), None)
                if entry is None:
                    entry = ledger.DifferentialEntry(cand, "unknown")
                    rat.differential.append(entry)
                for header, rows in _tables(body[cm.end():cend]):
                    for r in rows:
                        if len(r) >= 3:
                            entry.criteria.append(ledger.Criterion(r[0], r[1], _ids(r[2])))
        elif h.startswith("decision detail"):
            for line in body.splitlines():
                line = line.strip()
                if line.startswith("- Discriminator:"):
                    txt = line[len("- Discriminator:"):].strip()
                    idm = re.search(r"`\[(.*?)\]`", txt)
                    rat.discriminators.append({"text": re.sub(r"`\[.*?\]`", "", txt).strip(), "ids": _ids(idm.group(1)) if idm else []})
                elif line.startswith("- Unresolved:"):
                    rat.unresolved.append(line[len("- Unresolved:"):].strip())
                elif line.startswith("- Would change the diagnosis:"):
                    rat.would_change.append(line[len("- Would change the diagnosis:"):].strip())
    fm = re.search(r"Arm B thinking \(verbatim\):\s*```\n(.*?)```", block, re.S)
    if fm:
        rat.thinking = fm.group(1)
    return rat


def parse_ablation(block: str) -> ledger.Ablation | None:
    m = re.search(r"delivered diagnosis without them:\s*\*\*(.+?)\*\*\s*\(was (.+?)\)\s*·\s*changed:\s*(True|False)", block)
    removed: list[str] = []
    for header, rows in _tables(block):
        if header and header[0].lower() == "ids":
            for r in rows:
                removed += _ids(r[0])
            break
    if not m and not removed:
        return None
    return ledger.Ablation(removed, m.group(2).strip() if m else None, m.group(1).strip() if m else None, (m.group(3) == "True") if m else None)


def parse_markdown(text: str) -> tuple[ledger.LedgerCase, ledger.LedgerTrace]:
    from .copied_text import looks_copied, normalise
    if looks_copied(text):
        text = normalise(text)
    parts = _split_h2(text)
    head = text[: _H2.search(text).start()] if _H2.search(text) else text
    case_id = (re.search(r"Case:\s*`([^`]+)`", head) or re.search(r"case[_ ]?(\d+)", head, re.I))
    truth = re.search(r"ground truth:\s*\*\*(.+?)\*\*", head)
    model = re.search(r"Model:\s*`([^`]+)`", head)
    allowed_n = re.search(r"allowed citation ids:\s*(\d+)", head)
    facts, candidates = parse_facts(parts.get("1", ""))
    cm = re.search(r"^Candidate answers:\s*(.+?)\s*$", head, re.M)
    if cm:
        listed = [c.strip() for c in cm.group(1).split(";") if c.strip()]
        candidates = listed + [c for c in candidates if c not in listed]
    thinking_block = parts.get("2", "")
    fm = _FENCE.search(thinking_block)
    thinking = fm.group(1) if fm else thinking_block.strip()
    report = parse_report(parts.get("3", ""))
    rationale = parse_rationale(parts.get("4", "")) if "4" in parts else None
    ablation = parse_ablation(parts.get("5", "")) if "5" in parts else None
    allowed = {f.id for f in facts}
    case = ledger.LedgerCase(case_id.group(1) if case_id else "case", truth.group(1).strip() if truth else None, candidates, facts, allowed,
                             {"model": model.group(1) if model else None, "allowed_ids_declared": int(allowed_n.group(1)) if allowed_n else None,
                              "source_format": "enable-md"})
    trace = ledger.LedgerTrace(thinking, report, rationale, ablation, {"model": model.group(1) if model else None, "source_format": "enable-md"})
    return case, trace


# ----------------------------------------------------------------------------- the inverse: write an artefact

def _md_cell(x) -> str:
    return str(x if x is not None else "").replace("|", "\\|").replace("\n", " ")


def _table(header: list[str], rows: list[list]) -> list[str]:
    out = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    out += ["| " + " | ".join(_md_cell(c) for c in r) + " |" for r in rows]
    return out


def render_artefact(case: ledger.LedgerCase, trace: ledger.LedgerTrace, repeat: int = 1, model: str | None = None,
                    raw_report: dict | None = None, audit_lines: list[str] | None = None) -> str:
    """Write a case and a trace as the per-case Markdown artefact `parse_markdown` reads: fact tables with ids, the thinking,
    the delivered report (with its raw JSON and dropped segments), the rationale and the ablation. Facts that share a
    (section, field, value, evidence) row with consecutive ids are kept as separate rows; pass `raw_report` to control the
    JSON block (default: the report's sections, including dropped segments, under the engine's key names)."""
    model = model or (trace.meta.get("model") if trace.meta else None) or (case.meta.get("model") if case.meta else None) or "engine"
    out: list[str] = [f"# Reasoning trace — {case.case_id} — repeat {repeat}", "",
                      f"- Case: `{case.case_id}` · ground truth: **{case.truth or 'unknown'}**",
                      f"- Model: `{model}` · think A/C: `medium` · think B: `medium`",
                      f"- Facts: {len(case.facts)} total — context={sum(1 for f in case.facts if f.source == 'context')}, "
                      f"patient={sum(1 for f in case.facts if f.source == 'patient')}, who={sum(1 for f in case.facts if f.source == 'who')} · "
                      f"allowed citation ids: {len(case.allowed_ids or {f.id for f in case.facts})}", "",
                      "## 1. Available information (what the model was given)", ""]
    groups: dict[tuple[str, str], list[ledger.Fact]] = {}
    for f in case.facts:
        if f.source != "who":
            groups.setdefault((f.source, f.section), []).append(f)
    for (source, section), facts in groups.items():
        title = section.replace("_", " ")
        if source == "context" and "context" not in title.lower():
            title += " context"
        out.append(f"### {title} ({len(facts)} facts)")
        out.append("")
        if source == "context":
            out += _table(["ids", "field", "value"], [[f.id, f.field, f.value] for f in facts])
        else:
            out += _table(["ids", "field", "value", "evidence snippet"], [[f.id, f.field, f.value, f.evidence] for f in facts])
        out.append("")
    who = [f for f in case.facts if f.source == "who"]
    if who:
        cands = list(dict.fromkeys(f.candidate or f.section for f in who))
        out.append(f"### Reference criteria ({len(who)} facts across {len(cands)} candidates)")
        out.append("")
        for cand in cands:
            out.append(f"**{cand}**")
            out.append("")
            rows = []
            for f in who:
                if (f.candidate or f.section) != cand:
                    continue
                if rows and rows[-1][1] == f.field and rows[-1][2] == f.value:
                    rows[-1][0] += f", {f.id}"       # one row, several ids
                else:
                    rows.append([f.id, f.field, f.value])
            out += _table(["ids", "field", "value (truncated)"], rows)
            out.append("")
    out += ["## 2. Model's own reasoning (arm A thinking, verbatim)", "", "```", trace.thinking.rstrip("\n"), "```", ""]
    rep = trace.report
    out += ["## 3. Delivered report (arm A raw output replayed through the engine parser)", ""]
    out.append(f"predicted_diagnosis raw: **{rep.decision or ''}** · delivered: **{rep.delivered_decision or rep.decision or ''}** · "
               f"contract_valid: {bool(rep.contract_valid)}" + (f" · failure_kind: `{rep.failure_kind}`" if rep.failure_kind else ""))
    out.append("")
    for sec in rep.sections:
        out.append(f"**{sec.title}**")
        out.append("")
        for seg in sec.segments:
            out.append(f"- {seg.text} `[{', '.join(seg.citation_ids)}]`" if seg.citation_ids else f"- {seg.text}")
        out.append("")
    if rep.dropped_segments:
        out.append("Removed by post-processing (uncited informative segments the model wrote but the engine deleted):")
        out += [f"- {d['section']}: {d['text']}" for d in rep.dropped_segments]
        out.append("")
    if raw_report is None:
        raw_sections = []
        for sec in rep.sections:
            segs = [{"text": g.text, "citation_ids": list(g.citation_ids)} for g in sec.segments]
            segs += [{"text": d["text"], "citation_ids": []} for d in rep.dropped_segments if d["section"] == sec.title.rstrip(":")]
            raw_sections.append({"title": sec.title, "segments": segs})
        raw_report = {"predicted_diagnosis": rep.decision, "sections": raw_sections}
    out += ["Raw model JSON:", "", "```json", json.dumps(raw_report, indent=2, ensure_ascii=False), "```", ""]
    rat = trace.rationale
    if rat is not None:
        out += ["## 4. Structured rationale (arm B)", "",
                f"Decision: **{rat.decision or ''}**" + (f" · confidence: {rat.confidence}" if rat.confidence else "") +
                f" · agrees with delivered report: {rat.decision == (rep.delivered_decision or rep.decision)}", ""]
        if rat.key_findings:
            out += ["### Key findings", ""] + _table(["modality", "finding", "ids"],
                                                     [[k.get("modality", ""), k.get("description", ""), ", ".join(k.get("ids", []))] for k in rat.key_findings]) + [""]
        out += ["### Differential", ""] + _table(["diagnosis", "verdict", "supporting", "contradicting", "criteria", "rationale"],
                                                 [[d.diagnosis, d.verdict, ", ".join(d.supporting), ", ".join(d.contradicting),
                                                   f"met {sum(c.status == 'met' for c in d.criteria)} / not met {sum(c.status == 'not_met' for c in d.criteria)} / "
                                                   f"n.a. {sum(c.status not in ('met', 'not_met') for c in d.criteria)}", d.rationale] for d in rat.differential]) + [""]
        out += ["### Reference criteria, per candidate", ""]
        for d in rat.differential:
            if not d.criteria:
                continue
            out += [f"**{d.diagnosis}** ({d.verdict})", ""] + _table(["criterion", "status", "ids"], [[c.criterion, c.status, ", ".join(c.ids)] for c in d.criteria]) + [""]
        out += ["### Decision detail", ""]
        out += [f"- Discriminator: {d['text']} `[{', '.join(d.get('ids', []))}]`" for d in rat.discriminators]
        out += [f"- Unresolved: {u}" for u in rat.unresolved]
        out += [f"- Would change the diagnosis: {w}" for w in rat.would_change]
        out.append("")
        if rat.thinking:
            out += ["Arm B thinking (verbatim):", "", "```", rat.thinking.rstrip("\n"), "```", ""]
    abl = trace.ablation
    if abl is not None:
        by = case.by_id()
        out += ["## 5. Discriminator ablation (arm C)", "",
                f"Removed {len(abl.removed_ids)} fact(s) named as key discriminators; delivered diagnosis without them: "
                f"**{abl.decision_after or ''}** (was {abl.decision_before or ''}) · changed: {bool(abl.changed)}", ""]
        out += _table(["ids", "source", "field", "value"], [[i, by[i].source if i in by else "", by[i].field if i in by else "", by[i].value if i in by else ""]
                                                            for i in abl.removed_ids]) + [""]
    if audit_lines:
        out += ["## 6. Audit checks", ""] + list(audit_lines) + [""]
    return "\n".join(out)
