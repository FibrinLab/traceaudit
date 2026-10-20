"""Answer parsing, grounding labels and knowledge verifiers (spec 04 §2-5)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Protocol

from . import lexicon as lex_mod
from . import segment as seg_mod
from .lexicon import Lexicon
from .schema import Claim, Evidence, GroundingRecord, KnowledgeCheck, Trace
from .textutil import split_sentences

_DIAG_LINE = re.compile(r"^\s*\**\s*(?:integrated |final |overall |most likely |working )?diagnosis\s*\**\s*[:\-–]\s*\**\s*(.+?)\s*\**\s*$",
                        re.IGNORECASE | re.MULTILINE)


@dataclass
class ParsedAnswer:
    entity: str = "UNRESOLVED"
    entity_raw: str | None = None
    subtype: str | None = None
    hedged: bool = False
    entities_named: list[str] = field(default_factory=list)
    diagnosis_line: str | None = None


def parse_answer(answer: str, lexicon: Lexicon | None = None) -> ParsedAnswer:
    lx = lexicon or lex_mod.load()
    pa = ParsedAnswer()
    if not answer or not answer.strip():
        return pa
    all_ents = lx.find_entities(answer)
    pa.entities_named = sorted({m.entity for m in all_ents})
    m = _DIAG_LINE.search(answer)
    focus: str
    if m:
        focus = m.group(1)
        pa.diagnosis_line = focus
        ents = lx.find_entities(focus)
    else:
        focus = ""
        ents = []
        for s, e in split_sentences(answer):
            ents = lx.find_entities(answer[s:e])
            if ents:
                focus = answer[s:e]
                break
        if not ents and all_ents:
            counts: dict[str, int] = {}
            for e_ in all_ents:
                counts[e_.entity] = counts.get(e_.entity, 0) + 1
            best = max(counts, key=lambda k: (counts[k], -pa.entities_named.index(k)))
            ents = [e_ for e_ in all_ents if e_.entity == best][:1]
            focus = answer
    if ents:
        first = ents[0]
        pa.entity, pa.subtype, pa.entity_raw = first.entity, first.subtype, first.text
    distinct = {e_.entity for e_ in ents}
    hedge_a = len(distinct) >= 2
    hedge_b = bool(focus) and lx.has_phrase("hedge", focus)
    hedge_c = bool(re.search(r"\?\s*[A-Za-z]", focus or ""))
    if not hedge_b and focus and "most consistent with" in focus.lower() and len(pa.entities_named) >= 2:
        hedge_b = True
    if not m and pa.entity != "UNRESOLVED" and not hedge_b:
        # no diagnosis line: look at the sentence naming the primary entity
        for s, e in split_sentences(answer):
            if any(s <= x.start < e for x in all_ents if x.entity == pa.entity):
                hedge_b = lx.has_phrase("hedge", answer[s:e])
                break
    pa.hedged = bool(hedge_a or hedge_b or hedge_c)
    return pa


class Verifier(Protocol):
    name: str
    version: str

    def verify(self, claim: Claim, trace: Trace, lexicon: Lexicon) -> KnowledgeCheck | None: ...


class LexicalVerifier:
    name = "lexical"
    version = "1"

    def verify(self, claim: Claim, trace: Trace, lexicon: Lexicon) -> KnowledgeCheck | None:
        ents = set(claim.entities)
        polar = [a for a in claim.assertions if a.polarity]
        if len(ents) != 1 or not polar:
            return KnowledgeCheck("abstain", self.name, "needs exactly one entity and >=1 assertion")
        entity = next(iter(ents))
        verdicts = []
        evid = []
        for a in polar:
            exp = lexicon.expected(a.finding_id, entity)
            if exp in ("pos", "neg"):
                verdicts.append(exp == a.polarity)
                evid.append(f"{a.finding_id}@{entity}={exp}")
        if not verdicts:
            return KnowledgeCheck("abstain", self.name, "table cell var/missing")
        if all(verdicts):
            return KnowledgeCheck("consistent", self.name, "; ".join(evid))
        return KnowledgeCheck("inconsistent", self.name, "; ".join(evid))


class RetrievalVerifier:
    name = "retrieval"
    version = "1"
    _NEG = re.compile(r"\b(not|no|negative|absent|lack|without|rarely|unusual)\b")

    def verify(self, claim: Claim, trace: Trace, lexicon: Lexicon) -> KnowledgeCheck | None:
        if not trace.retrieved or len(set(claim.entities)) != 1:
            return KnowledgeCheck("abstain", self.name, "no retrieval or ambiguous entity")
        entity = claim.entities[0]
        polar = [a for a in claim.assertions if a.polarity]
        if not polar:
            return KnowledgeCheck("abstain", self.name, "no assertion")
        for chunk in trace.retrieved:
            txt = chunk.text
            ents = {m.entity for m in lexicon.find_entities(txt)}
            if entity not in ents:
                continue
            for a in polar:
                for sp in lexicon.mentions_marker(txt, a.finding_id):
                    window = txt[max(0, sp.start - 60):sp.end + 40]
                    negated = bool(self._NEG.search(window))
                    chunk_pol = "neg" if negated else "pos"
                    verdict = "consistent" if chunk_pol == a.polarity else "inconsistent"
                    return KnowledgeCheck(verdict, self.name, window.strip(), 0.3)
        return KnowledgeCheck("abstain", self.name, "not addressed")


def ground(trace: Trace, truth_after: dict[str, str], claims: list[Claim], finding_spans: dict[str, list[dict]] | None = None,
           entity_after: str | None = None, verifier: Verifier | None = None, lexicon: Lexicon | None = None) -> GroundingRecord:
    """Label factual claims in place and return the per-trace record [PRE-REG]."""
    lx = lexicon or lex_mod.load()
    rec = GroundingRecord(trace_key=trace.trace_key, case_id=trace.case_id, variant=trace.variant,
                          effort=trace.effort, run=trace.run)
    if not trace.ok:
        rec.error = trace.meta.error
        return rec
    spans = finding_spans or {}
    contradicted: set[str] = set()
    unsupported: set[str] = set()
    for c in claims:
        rec.n_claims += 1
        if c.type == "factual":
            rec.n_factual += 1
            if "has_inference" in c.flags:
                rec.n_has_inference += 1
            label, evidence = _label(c, truth_after, spans)
            c.label = label
            c.evidence = evidence
            if label == "ambiguous":
                rec.n_ambiguous += 1
            else:
                if label == "supported":
                    rec.n_supported += 1
                elif label == "contradicted":
                    rec.n_contradicted += 1
                    contradicted.update(e.finding_id for e in evidence if e.truth and e.claimed != e.truth)
                else:
                    rec.n_unsupported += 1
                    unsupported.update(e.finding_id for e in evidence if e.truth is None)
                if "has_inference" not in c.flags:
                    rec.n_graded_no_inference += 1
                    if label == "supported":
                        rec.n_supported_no_inference += 1
        elif c.type == "knowledge":
            rec.n_knowledge += 1
            if verifier is not None:
                kc = verifier.verify(c, trace, lx)
                c.knowledge_check = kc
                if kc:
                    if kc.verdict == "consistent":
                        rec.knowledge_consistent += 1
                    elif kc.verdict == "inconsistent":
                        rec.knowledge_inconsistent += 1
                    else:
                        rec.knowledge_abstain += 1
        elif c.type == "inferential":
            rec.n_inferential += 1
        else:
            rec.n_other += 1
    denom = rec.n_supported + rec.n_contradicted + rec.n_unsupported
    rec.grounding_rate = rec.n_supported / denom if denom else None
    rec.contradicted_findings = sorted(contradicted)
    rec.unsupported_findings = sorted(unsupported)
    pa = parse_answer(trace.answer, lx)
    rec.answer_entity = pa.entity
    rec.answer_entity_raw = pa.entity_raw
    rec.answer_subtype = pa.subtype
    rec.answer_hedged = pa.hedged
    rec.answer_correct = (pa.entity == entity_after) if entity_after else None
    rec.trace_conclusion_entity = seg_mod.trace_conclusion(claims, trace.reasoning, lx)
    rec.trace_answer_agree = (rec.trace_conclusion_entity == pa.entity) if rec.trace_conclusion_entity else None
    return rec


def _label(claim: Claim, truth: dict[str, str], spans: dict[str, list[dict]]) -> tuple[str, list[Evidence]]:
    evidence: list[Evidence] = []
    any_conflict = False
    any_contra = False
    any_unsup = False
    for a in claim.assertions:
        if a.polarity is None:
            continue
        if "CONFLICT" in a.warnings:
            any_conflict = True
        t = truth.get(a.finding_id)
        sp = spans.get(a.finding_id, [])
        ev = Evidence(finding_id=a.finding_id, claimed=a.polarity, truth=t,
                      report=sp[0]["report"] if sp else None,
                      span=[sp[0]["start"], sp[0]["end"]] if sp else None)
        evidence.append(ev)
        if t is None:
            any_unsup = True
        elif t != a.polarity:
            any_contra = True
    if any_conflict:
        return "ambiguous", evidence
    if any_contra:
        return "contradicted", evidence
    if any_unsup:
        return "unsupported", evidence
    return "supported", evidence
