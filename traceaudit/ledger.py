"""Fact ledger: the structured core of trace analytics.

A case is a set of *facts* with ids (patient findings, clinical context, reference criteria). A trace *cites* those ids
in its reasoning, its delivered report and its rationale. Every check here is a question about facts and citations:

- do the cited ids exist, and does the sentence that cites a fact state the value the fact has?
- which facts were never referenced (ignored), and were they informative?
- did the reasoning consider more than one candidate answer?
- does the favoured answer cite the reference criteria it rests on, and do "contradicting" citations really contradict?
- when the stated discriminators are removed (ablation), does the answer change?

Free-text documents are turned into facts by the lexicon extractor (see `extract`); pipelines that already emit
structured facts, like the ENABLE-AI engine, are ingested directly (see `importers`). Standard library only.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from . import extract
from .lexicon import Lexicon

ID_RE = re.compile(r"\b([a-z]{1,3}_\d{1,5})\b")

POS_VALUES = {"positive", "present", "detected", "weak", "dim", "bright", "strong", "moderate", "partial", "yes", "true", "abnormal",
              "elevated", "high", "increased", "clonal", "rearranged"}
NEG_VALUES = {"negative", "absent", "not detected", "no", "false", "normal", "wild-type", "wild type", "wildtype", "none", "not present"}
UNTESTED_VALUES = {"not performed", "not mentioned", "not assessed", "not tested", "unknown", "n/a", "na", "", "not available", "not done"}


def value_polarity(value: Any) -> str:
    """pos | neg | untested | other (numeric or categorical values such as 'unmutated' are 'other' unless listed)."""
    v = str(value).strip().lower()
    if v in UNTESTED_VALUES:
        return "untested"
    if v in NEG_VALUES:
        return "neg"
    if v in POS_VALUES:
        return "pos"
    if v.startswith("no ") or v.startswith("not "):
        return "neg"
    return "other"


# ----------------------------------------------------------------------------- records

@dataclass
class Fact:
    id: str
    source: str            # patient | context | who
    section: str           # modality / document section; for who facts the candidate answer
    field: str
    value: str
    evidence: str = ""
    candidate: str | None = None   # who facts: which answer they describe

    @property
    def polarity(self) -> str:
        return value_polarity(self.value)

    @property
    def informative(self) -> bool:
        return self.source in ("patient", "context") and self.polarity != "untested"

    def to_dict(self) -> dict:
        return {"id": self.id, "source": self.source, "section": self.section, "field": self.field, "value": self.value,
                "evidence": self.evidence, "candidate": self.candidate, "polarity": self.polarity, "informative": self.informative}


@dataclass
class Segment:
    text: str
    citation_ids: list[str] = field(default_factory=list)


@dataclass
class Section:
    title: str
    segments: list[Segment] = field(default_factory=list)


@dataclass
class Report:
    decision: str | None
    sections: list[Section] = field(default_factory=list)
    delivered_decision: str | None = None
    contract_valid: bool | None = None
    failure_kind: str | None = None
    dropped_segments: list[dict] = field(default_factory=list)


@dataclass
class Criterion:
    criterion: str
    status: str            # met | not_met | not_assessable
    ids: list[str] = field(default_factory=list)


@dataclass
class DifferentialEntry:
    diagnosis: str
    verdict: str
    supporting: list[str] = field(default_factory=list)
    contradicting: list[str] = field(default_factory=list)
    rationale: str = ""
    criteria: list[Criterion] = field(default_factory=list)


@dataclass
class Rationale:
    decision: str | None
    confidence: str | None = None
    key_findings: list[dict] = field(default_factory=list)      # {description, ids, modality}
    differential: list[DifferentialEntry] = field(default_factory=list)
    discriminators: list[dict] = field(default_factory=list)    # {text, ids}
    unresolved: list[str] = field(default_factory=list)
    would_change: list[str] = field(default_factory=list)
    thinking: str = ""


@dataclass
class Ablation:
    removed_ids: list[str]
    decision_before: str | None
    decision_after: str | None
    changed: bool | None = None


@dataclass
class LedgerCase:
    case_id: str
    truth: str | None
    candidates: list[str]
    facts: list[Fact]
    allowed_ids: set[str] = field(default_factory=set)
    meta: dict = field(default_factory=dict)

    def fact(self, fid: str) -> Fact | None:
        return next((f for f in self.facts if f.id == fid), None)

    def by_id(self) -> dict[str, Fact]:
        return {f.id: f for f in self.facts}


@dataclass
class LedgerTrace:
    thinking: str
    report: Report
    rationale: Rationale | None = None
    ablation: Ablation | None = None
    meta: dict = field(default_factory=dict)


# ----------------------------------------------------------------------------- aliases and an ad-hoc lexicon

def field_aliases(fieldname: str) -> list[str]:
    """Surface forms a sentence might use for a fact field: 'del_11q' -> del(11q), del 11q; 'ATM_variant' -> ATM variant, ATM."""
    f = fieldname.strip()
    out = [f]
    low = f.lower()
    m = re.fullmatch(r"del_(\d+)([pq])", low)
    if m:
        out += [f"del({m.group(1)}{m.group(2)})", f"del {m.group(1)}{m.group(2)}", f"{m.group(1)}{m.group(2)} deletion", f"deletion of {m.group(1)}{m.group(2)}"]
    m = re.fullmatch(r"t_(\d+)_(\d+)", low)
    if m:
        out += [f"t({m.group(1)};{m.group(2)})"]
    m = re.fullmatch(r"gain_of_(\d+)", low)
    if m:
        out += [f"trisomy {m.group(1)}", f"+{m.group(1)}", f"gain of {m.group(1)}"]
    if low.endswith("_variant"):
        gene = f[: -len("_variant")]
        out += [f"{gene} variant", f"{gene} mutation", gene.replace("_", " "), gene.split("_")[0]]
    if "_" in f:
        # every mix of space and hyphen for the underscores: on_call_note -> "on call note", "on-call note", ...
        parts = f.split("_")
        if len(parts) <= 4:
            import itertools
            for seps in itertools.product((" ", "-"), repeat=len(parts) - 1):
                out.append("".join(p + sep for p, sep in zip(parts, seps)) + parts[-1])
        else:
            out += [f.replace("_", " "), f.replace("_", "-")]
    if low == "smear_cell":
        out += ["smudge cells", "smear cells"]
    if low == "small_size":
        out += ["small cells", "small mature"]
    if low == "prominent_nucleoli":
        out += ["prominent nucleoli", "nucleoli"]
    if low == "ighv_mutated":
        out += ["IGHV"]
    if low == "lymph":
        out += ["lymphocyte count", "lymphocytosis", "lymph count"]
    seen: list[str] = []
    for a in out:
        if a and a.lower() not in {s.lower() for s in seen}:
            seen.append(a)
    return seen


def lexicon_from_case(case: LedgerCase, base: Lexicon | None = None) -> Lexicon:
    """A throwaway lexicon whose findings are the case's patient/context fields, so the text extractor can grade sentences.

    A case whose fields *are* the base lexicon's finding ids (`meta["lexicon_fields"]`, set by `ledger_adapters`) is graded
    with the base lexicon itself: same aliases, phrases, numeric rules and entity names as the text path."""
    from . import lexicon as lex_mod
    if base is not None and case.meta.get("lexicon_fields"):
        return base
    phrases = base.phrases if base else _default_phrases()
    polarity = base.polarity if base else _default_polarity()
    findings = []
    seen = set()
    for f in case.facts:
        if f.source not in ("patient", "context") or f.field in seen:
            continue
        seen.add(f.field)
        aliases = [a for a in field_aliases(f.field) if a.lower() not in {x.lower() for ff in findings for x in ff["aliases"]}]
        if not aliases:
            continue
        # A polar value word that the cue grammar does not know ("elevated", "high", "normal", "present") becomes whole-phrase
        # forms, so "error rate elevated" and "database latency normal" read as assertions outside the reference domain.
        pos_phrases: list[str] = []
        neg_phrases: list[str] = []
        polar = any(g.field == f.field and g.polarity in ("pos", "neg") for g in case.facts)
        if polar:
            # the fact's own value word plus the generic polar words, so a sentence can also *contradict* the fact
            # ("CPU elevated" against a fact recorded as Normal)
            words = {"pos": {"elevated", "high", "increased", "raised", "abnormal", "present", "detected"},
                     "neg": {"normal", "absent", "not detected", "none", "unremarkable"}}
            for g in case.facts:
                if g.field == f.field and g.polarity in ("pos", "neg"):
                    word = str(g.value).strip().lower()
                    if word and word not in {"positive", "negative", "+", "-"}:
                        words[g.polarity].add(word)
            for pol, target in (("pos", pos_phrases), ("neg", neg_phrases)):
                for a in aliases:
                    for word in sorted(words[pol]):
                        for phrase in (f"{a} {word}", f"{word} {a}", f"{a} is {word}", f"{a} was {word}"):
                            if phrase.lower() not in {x.lower() for x in target}:
                                target.append(phrase)
        findings.append({"id": f.field, "display": f.field, "kind": "fact", "modality": f.section, "aliases": aliases,
                         "pos_phrases": pos_phrases, "neg_phrases": neg_phrases, "intensity": False, "numeric_rule": None, "default_polarity": None,
                         "pos_text": None, "neg_text": None, "notes": ""})
    entities = [{"id": c, "display": c, "in_scope": True, "parent": None, "aliases": [c] + _candidate_aliases(c)} for c in case.candidates] or \
               [{"id": "ANSWER", "display": "answer", "in_scope": True, "parent": None, "aliases": ["answer"]}]
    data = {"version": "ledger", "domain": "ledger", "entities": entities, "findings": findings, "polarity": polarity,
            "discriminators": {}, "linked": {}, "confusion": {}, "phrases": phrases, "sections": []}
    return lex_mod.Lexicon(data)


def _candidate_aliases(c: str) -> list[str]:
    out = []
    if "/" in c:
        out += [p.strip() for p in c.split("/") if p.strip()]
    return out


def _default_phrases() -> dict:
    return {"hedge": ["differential", "cannot exclude", "versus", "vs", "possible", "uncertain", "indeterminate", "favour", "favor"],
            "acknowledge_cue": ["referring", "suggested", "working diagnosis", "suspected"],
            "knowledge": ["typically", "usually", "classically", "criteria", "defined by", "requires", "is characterised by", "is characterized by"],
            "patient_reference": ["this case", "this patient", "the patient", "we have", "given the"],
            "conditional": ["if ", " were ", " would ", "assuming"],
            "inference": ["therefore", "thus", "hence", "suggests", "consistent with", "supports", "indicates", "likely", "fits"],
            "question": ["?", "whether"], "conclusion": ["diagnosis", "conclude", "overall", "final"]}


def _default_polarity() -> dict:
    return {"pos_suffix": ["+", "positive", "present"], "neg_suffix": ["-", "negative", "absent"],
            "intensity_pos": ["dim", "weak", "weakly", "partial", "moderate", "bright", "strong"], "intensity_dim": [], "intensity_bright": []}


# ----------------------------------------------------------------------------- grading

def grade_segment(seg: Segment, case: LedgerCase, lx: Lexicon) -> dict:
    """For one report segment: each cited fact -> agree | disagree | unverifiable | not_found; plus uncited assertions."""
    facts = case.by_id()
    asserted = [a for a in extract.extract_assertions(seg.text, lx) if a.polarity]
    by_field: dict[str, str] = {}
    for a in asserted:
        by_field.setdefault(a.finding_id, a.polarity)
    cited = []
    for cid in seg.citation_ids:
        f = facts.get(cid)
        if f is None:
            cited.append({"id": cid, "grade": "not_found", "field": None, "value": None})
            continue
        if f.source == "who":
            cited.append({"id": cid, "grade": "reference", "field": f.field, "value": f.value, "candidate": f.candidate})
            continue
        stated = by_field.get(f.field)
        fp = f.polarity
        if fp == "other" and value_stated_literally(seg.text, f):
            cited.append({"id": cid, "grade": "agree", "field": f.field, "value": f.value, "stated": f.value})
        elif stated is None or fp in ("other", "untested"):
            mentioned = any(a.lower() in seg.text.lower() for a in field_aliases(f.field))
            cited.append({"id": cid, "grade": "unverifiable" if mentioned or fp == "other" else "not_mentioned", "field": f.field, "value": f.value, "stated": stated})
        else:
            cited.append({"id": cid, "grade": "agree" if stated == fp else "disagree", "field": f.field, "value": f.value, "stated": stated})
    cited_fields = {facts[c].field for c in seg.citation_ids if c in facts}
    uncited = []
    for fld, pol in by_field.items():
        if fld in cited_fields:
            continue
        candidates = [f for f in case.facts if f.field == fld and f.source in ("patient", "context")]
        if candidates:
            f = candidates[0]
            uncited.append({"field": fld, "stated": pol, "fact_id": f.id, "value": f.value,
                            "grade": "agree" if f.polarity == pol else ("disagree" if f.polarity in ("pos", "neg") else "unverifiable")})
        else:
            uncited.append({"field": fld, "stated": pol, "fact_id": None, "value": None, "grade": "unknown_fact"})
    return {"text": seg.text, "citation_ids": list(seg.citation_ids), "cited": cited, "uncited_assertions": uncited,
            "informative": bool(asserted) or bool(re.search(r"[A-Za-z]{3,}", seg.text))}


def value_stated_literally(text: str, f: Fact, window: int = 40) -> bool:
    """For categorical values (e.g. IGHV 'unmutated', a numeric count): the value appears next to the field name."""
    low = text.lower()
    val = str(f.value).strip().lower()
    if not val or len(val) < 2:
        return False
    for a in field_aliases(f.field):
        for m in re.finditer(r"(?<![A-Za-z0-9])" + re.escape(a.lower()) + r"(?![A-Za-z0-9])", low):
            around = low[max(0, m.start() - window): m.end() + window]
            if re.search(r"(?<![A-Za-z0-9])" + re.escape(val) + r"(?![A-Za-z0-9])", around):
                return True
    return False


def referenced_ids(text: str) -> set[str]:
    return set(ID_RE.findall(text or ""))


def facts_mentioned(text: str, case: LedgerCase, lx: Lexicon) -> set[str]:
    """Fact ids whose field is named in the text (by a field alias or one of the lexicon's aliases), regardless of polarity."""
    out: set[str] = set()
    low = text.lower()
    named = {t.finding_id for t in lx.marker_tokens(text)}
    for f in case.facts:
        if f.source not in ("patient", "context"):
            continue
        if f.field in named:
            out.add(f.id)
            continue
        for a in field_aliases(f.field):
            if len(a) >= 3 and re.search(r"(?<![A-Za-z0-9])" + re.escape(a.lower()) + r"(?![A-Za-z0-9])", low):
                out.add(f.id)
                break
    return out


def candidates_named(text: str, case: LedgerCase, lx: Lexicon | None = None) -> list[str]:
    """Candidates the text names, in candidate order: by their own name (or a slash-separated part of it), or, when a
    lexicon is given, by any of that lexicon's entity aliases."""
    low = text.lower()
    out = []
    by_lexicon = {m.entity for m in lx.find_entities(text)} if lx is not None else set()
    for c in case.candidates:
        if c in by_lexicon:
            out.append(c)
            continue
        for a in [c] + _candidate_aliases(c):
            if re.search(r"(?<![A-Za-z0-9])" + re.escape(a.lower()) + r"(?![A-Za-z0-9])", low):
                out.append(c)
                break
    return out


def audit(case: LedgerCase, trace: LedgerTrace, base_lexicon: Lexicon | None = None) -> dict:
    """Run every fact-level check. Returns a JSON-serialisable result with checks, grades, coverage and metrics."""
    lx = lexicon_from_case(case, base_lexicon)
    facts = case.by_id()
    allowed = set(case.allowed_ids) | set(facts)
    checks: list[dict] = []

    def check(cid: str, title: str, status: str, detail: str = "") -> None:
        checks.append({"id": cid, "title": title, "status": status, "detail": detail})

    # --- report segments
    graded_sections = []
    all_cited: list[str] = []
    disagreements = 0
    agreements = 0
    unverifiable = 0
    uncited_assertions = 0
    uncited_segments = 0
    for sec in trace.report.sections:
        gs = []
        for seg in sec.segments:
            g = grade_segment(seg, case, lx)
            gs.append(g)
            all_cited += seg.citation_ids
            for c in g["cited"]:
                if c["grade"] == "agree":
                    agreements += 1
                elif c["grade"] == "disagree":
                    disagreements += 1
                elif c["grade"] in ("unverifiable", "not_mentioned"):
                    unverifiable += 1
            uncited_assertions += len(g["uncited_assertions"])
            if not seg.citation_ids and g["informative"]:
                uncited_segments += 1
        graded_sections.append({"title": sec.title, "segments": gs})
    bad_ids = sorted({c for c in all_cited if c not in allowed})
    check("citations_exist", "Every cited id exists", "PASS" if not bad_ids else "FAIL", "" if not bad_ids else f"unknown ids: {', '.join(bad_ids)}")
    check("citations_agree", "Cited facts are stated with their recorded value", "PASS" if disagreements == 0 else "FAIL",
          f"{agreements} agree, {disagreements} disagree, {unverifiable} unverifiable")
    check("segments_cited", "Every informative segment carries a citation", "PASS" if uncited_segments == 0 else "FAIL",
          f"{uncited_segments} informative segment(s) without citations")
    if trace.report.contract_valid is not None:
        check("report_contract", "Report contract valid (no engine warnings)", "PASS" if trace.report.contract_valid else "FAIL", trace.report.failure_kind or "")
    if trace.report.dropped_segments:
        check("nothing_dropped", "Nothing informative deleted by post-processing", "FAIL", f"{len(trace.report.dropped_segments)} segment(s) dropped")
    else:
        check("nothing_dropped", "Nothing informative deleted by post-processing", "PASS")
    summary = next((s for s in trace.report.sections if s.title.lower().startswith("summary")), None)
    # the three-segment summary is the ENABLE engine's report contract; only artefacts from it are held to it
    if summary is not None and (case.meta.get("source_format") == "enable-md" or trace.meta.get("source_format") == "enable-md"):
        heads = [seg.text.split(":")[0].strip().lower() for seg in summary.segments]
        missing = [h for h in ("diagnosis", "summary", "additional comments") if h not in heads]
        check("summary_structure", "Summary has Diagnosis, Summary and Additional comments", "PASS" if not missing else "FAIL",
              "" if not missing else "missing: " + ", ".join(missing))

    # --- decision
    decision = trace.report.delivered_decision or trace.report.decision
    if case.truth is not None and decision is not None:
        check("decision_matches_truth", "Delivered answer matches ground truth", "PASS" if decision == case.truth else "FAIL", f"{decision} vs {case.truth}")
    if trace.report.decision and trace.report.delivered_decision:
        check("decision_survived", "Raw answer survived post-processing unchanged",
              "PASS" if trace.report.decision == trace.report.delivered_decision else "FAIL", f"{trace.report.decision} -> {trace.report.delivered_decision}")

    # --- thinking
    thinking_ids = referenced_ids(trace.thinking)
    thinking_fields = facts_mentioned(trace.thinking, case, lx)
    named = candidates_named(trace.thinking, case, lx)
    check("thinking_present", "Thinking returned", "PASS" if trace.thinking.strip() else "FAIL", f"{len(trace.thinking)} characters")
    check("thinking_considers_alternatives", "Thinking considered more than one candidate answer",
          "PASS" if len(set(named)) > 1 else "FAIL", "named: " + (", ".join(sorted(set(named))) or "none"))
    unknown_in_thinking = sorted(i for i in thinking_ids if i not in allowed)
    check("thinking_ids_valid", "Thinking cites only allowed ids", "PASS" if not unknown_in_thinking else "FAIL", ", ".join(unknown_in_thinking))
    thinking_assertions = [a for a in extract.extract_assertions(trace.thinking, lx) if a.polarity]
    think_disagree = []
    for a in thinking_assertions:
        f = next((f for f in case.facts if f.field == a.finding_id and f.source in ("patient", "context")), None)
        if f and f.polarity in ("pos", "neg") and f.polarity != a.polarity:
            think_disagree.append(f"{f.field} stated {a.polarity}, recorded {f.value}")
    check("thinking_agrees", "Facts restated in thinking match their recorded values", "PASS" if not think_disagree else "FAIL", "; ".join(think_disagree[:8]))

    # --- rationale
    rat = trace.rationale
    rationale_ids: set[str] = set()
    if rat is not None:
        for kf in rat.key_findings:
            rationale_ids |= set(kf.get("ids", []))
        for d in rat.differential:
            rationale_ids |= set(d.supporting) | set(d.contradicting)
            for c in d.criteria:
                rationale_ids |= set(c.ids)
        for d in rat.discriminators:
            rationale_ids |= set(d.get("ids", []))
        if rat.decision and decision:
            check("rationale_agrees", "Rationale decision agrees with the delivered answer", "PASS" if rat.decision == decision else "FAIL", f"{rat.decision} vs {decision}")
        if rat.decision and case.truth:
            check("rationale_matches_truth", "Rationale decision matches ground truth", "PASS" if rat.decision == case.truth else "FAIL", f"{rat.decision} vs {case.truth}")
        fav = [d.diagnosis for d in rat.differential if d.verdict == "favoured"]
        check("one_favoured", "Exactly one favoured answer and it equals the decision",
              "PASS" if len(fav) == 1 and fav[0] == rat.decision else "FAIL", ", ".join(fav) or "none favoured")
        listed = {d.diagnosis for d in rat.differential}
        missing = [c for c in case.candidates if c not in listed]
        check("differential_complete", "Differential covers every candidate", "PASS" if not missing else "FAIL",
              f"{len(listed)} listed" + ("" if not missing else "; missing " + ", ".join(missing)))
        bad_r = sorted(i for i in rationale_ids if i not in allowed)
        check("rationale_ids_valid", "Every rationale citation exists", "PASS" if not bad_r else "FAIL", ", ".join(bad_r))
        # contradicting evidence must be informative and must actually disagree with the candidate's expectation when known
        weak_contra = []
        for d in rat.differential:
            for cid in d.contradicting:
                f = facts.get(cid)
                if f is not None and not f.informative and f.source != "who":
                    weak_contra.append(f"{d.diagnosis}: {cid} ({f.field} = {f.value})")
        check("contradicting_evidence_informative", "Contradicting citations point at informative facts", "PASS" if not weak_contra else "FAIL",
              "; ".join(weak_contra[:8]))
        # criteria for the favoured answer
        if fav:
            fav_entry = next(d for d in rat.differential if d.diagnosis == fav[0])
            crit_ids = {i for c in fav_entry.criteria for i in c.ids}
            who_cited = [facts[i] for i in crit_ids if i in facts and facts[i].source == "who"]
            fields = sorted({f.field for f in who_cited})
            essential = [f for f in case.facts if f.source == "who" and f.candidate == fav[0] and "essential" in f.field]
            ok = any(f.field.startswith("essential") for f in who_cited) or not essential
            check("criteria_cited", "Reference essential criteria cited for the favoured answer", "PASS" if ok else "FAIL",
                  "cited fields: " + (", ".join(fields) or "none") + ("" if ok else f"; expected {', '.join(e.id for e in essential)}"))
            not_met = [c.criterion for c in fav_entry.criteria if c.status == "not_met"]
            check("favoured_criteria_met", "No essential criterion of the favoured answer is marked not met", "PASS" if not not_met else "FAIL", "; ".join(not_met))

    # --- coverage
    referenced = thinking_ids | thinking_fields | set(all_cited) | rationale_ids
    ignored = [f for f in case.facts if f.source in ("patient", "context") and f.id not in referenced]
    ignored_informative = [f for f in ignored if f.informative]
    check("coverage", "Every patient/context fact was referenced in thinking, report or rationale",
          "PASS" if not ignored else "FAIL", f"{len(ignored)} ignored, {len(ignored_informative)} of them informative")
    check("coverage_informative", "Every informative patient/context fact was referenced", "PASS" if not ignored_informative else "FAIL",
          ", ".join(f"{f.id} {f.field}={f.value}" for f in ignored_informative[:12]))

    # --- ablation
    abl = trace.ablation
    if abl is not None:
        changed = abl.changed if abl.changed is not None else (abl.decision_before != abl.decision_after)
        check("discriminators_load_bearing", "Stated discriminators are load-bearing (answer changes without them)",
              "PASS" if changed else "FAIL", f"{abl.decision_before} -> {abl.decision_after} after removing {len(abl.removed_ids)} fact(s)")
        if rat is not None:
            stated = {i for d in rat.discriminators for i in d.get("ids", [])}
            summary_cited = set()
            if summary is not None:
                for seg in summary.segments:
                    summary_cited |= set(seg.citation_ids)
            inter = stated & summary_cited
            union = stated | summary_cited
            jac = len(inter) / len(union) if union else None
            check("discriminators_in_summary", "Stated discriminators overlap the delivered summary citations",
                  "PASS" if inter else "FAIL", f"jaccard {jac:.3f}; shared {', '.join(sorted(inter)) or 'none'}" if jac is not None else "no citations")

    n_fail = sum(1 for c in checks if c["status"] == "FAIL")
    metrics = {
        "facts": len(case.facts), "patient_facts": sum(1 for f in case.facts if f.source == "patient"),
        "context_facts": sum(1 for f in case.facts if f.source == "context"), "reference_facts": sum(1 for f in case.facts if f.source == "who"),
        "cited_in_report": len(set(all_cited)), "cited_agree": agreements, "cited_disagree": disagreements, "cited_unverifiable": unverifiable,
        "uncited_assertions": uncited_assertions,
        # the text path's headline: agreeing citations over every graded citation (None when nothing was graded)
        "grounding_rate": agreements / graded if (graded := agreements + disagreements + unverifiable) else None,
        "thinking_chars": len(trace.thinking), "thinking_ids": len(thinking_ids), "thinking_fields": len(thinking_fields),
        "candidates_named_in_thinking": dict(Counter(named)), "ignored": len(ignored), "ignored_informative": len(ignored_informative),
        "checks_failed": n_fail, "checks_total": len(checks),
    }
    return {
        "case_id": case.case_id, "truth": case.truth, "decision": decision, "candidates": case.candidates,
        "checks": checks, "metrics": metrics, "sections": graded_sections,
        "facts": [{**f.to_dict(), "referenced_in_thinking": f.id in thinking_ids or f.id in thinking_fields,
                   "cited_in_report": f.id in set(all_cited), "cited_in_rationale": f.id in rationale_ids,
                   "ignored": f.id in {g.id for g in ignored}} for f in case.facts],
        "thinking": {"text": trace.thinking, "ids": sorted(thinking_ids), "candidates": named},
        "rationale": None if rat is None else {
            "decision": rat.decision, "confidence": rat.confidence, "key_findings": rat.key_findings,
            "differential": [{"diagnosis": d.diagnosis, "verdict": d.verdict, "supporting": d.supporting, "contradicting": d.contradicting,
                              "rationale": d.rationale, "criteria": [c.__dict__ for c in d.criteria]} for d in rat.differential],
            "discriminators": rat.discriminators, "unresolved": rat.unresolved, "would_change": rat.would_change},
        "ablation": None if abl is None else abl.__dict__,
    }


def review_rows(result: dict) -> list[dict]:
    """One row per citation grade and per uncited assertion in an audit result, for a human to scan for mis-grades."""
    rows: list[dict] = []
    for sec in result.get("sections", []):
        for seg in sec.get("segments", []):
            for c in seg.get("cited", []):
                rows.append({"case_id": result["case_id"], "section": sec["title"], "segment_text": seg["text"], "kind": "cited",
                             "fact_id": c.get("id"), "field": c.get("field"), "value": c.get("value"), "stated": c.get("stated"),
                             "grade": c.get("grade")})
            for u in seg.get("uncited_assertions", []):
                rows.append({"case_id": result["case_id"], "section": sec["title"], "segment_text": seg["text"], "kind": "uncited",
                             "fact_id": u.get("fact_id"), "field": u.get("field"), "value": u.get("value"), "stated": u.get("stated"),
                             "grade": u.get("grade")})
    return rows


REVIEW_COLUMNS = ["case_id", "section", "segment_text", "kind", "fact_id", "field", "value", "stated", "grade", "human_grade", "note"]


def audit_many(results: list[dict]) -> dict:
    """Aggregate audit results across artefacts: per-case verdicts, pass rate per check, and grade counts."""
    per_case = [{"case_id": r["case_id"], "decision": r["decision"], "truth": r["truth"],
                 "checks_failed": r["metrics"]["checks_failed"], "checks_total": r["metrics"]["checks_total"]} for r in results]
    checks: dict[str, dict] = {}
    for r in results:
        for ch in r["checks"]:
            row = checks.setdefault(ch["id"], {"title": ch["title"], "pass": 0, "fail": 0, "n": 0})
            row["n"] += 1
            row["pass" if ch["status"] == "PASS" else "fail"] += 1
    for row in checks.values():
        row["pass_rate"] = round(row["pass"] / row["n"], 4) if row["n"] else None
    cited: dict[str, int] = {}
    uncited: dict[str, int] = {}
    for r in results:
        for row in review_rows(r):
            target = cited if row["kind"] == "cited" else uncited
            target[row["grade"] or "unknown"] = target.get(row["grade"] or "unknown", 0) + 1
    decided = [r for r in results if r["truth"] is not None and r["decision"] is not None]
    return {"n": len(results), "per_case": per_case, "check_pass_rates": checks,
            "grade_counts": {"cited": cited, "uncited": uncited},
            "decision_matches_truth": {"n": len(decided), "matches": sum(1 for r in decided if r["decision"] == r["truth"])}}
