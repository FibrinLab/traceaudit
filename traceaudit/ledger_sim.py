"""A simulated model for fact-ledger cases: reads the rendered fact table, answers per the job's variant metadata,
and emits the ledger-v1 JSON contract with planted faults (spec 19 validation, mirroring simulate.SimParams).

The simulator never sees truth: the prompt is the rendered case; the variant kind, base answer, expected answer and
edited fact ids arrive out of band in `meta` (GenerateRequest.meta), exactly as for the text simulator.
"""
from __future__ import annotations

import hashlib
import json
import random
from dataclasses import dataclass, fields

from .clients.callable_ import CallableClient
from .importers.enable_md import parse_markdown
from .ledger import Fact, field_aliases
from .schema import variant_kind
from .simulate import SimParams


@dataclass
class LedgerSimParams(SimParams):
    p_contract_break: float = 0.0  # reply in prose instead of the JSON contract
    p_ablation_ignored: float = 0.0  # keep the answer when the stated discriminators are removed

    @classmethod
    def uniform(cls, p: float, **kw) -> "LedgerSimParams":
        d = {f.name: p for f in fields(cls) if f.name.startswith("p_")}
        d.update(kw)
        return cls(**d)


class LedgerSimulatedModel:
    """Callable model: fn(system, user, effort, seed, meta=...) -> dict(reasoning, answer)."""

    def __init__(self, params: LedgerSimParams | None = None, seed: int = 0):
        self.params = params or LedgerSimParams()
        self.seed = seed

    @classmethod
    def client(cls, params: LedgerSimParams | dict | None = None, seed: int = 0, **kw) -> CallableClient:
        if isinstance(params, dict):
            params = LedgerSimParams(**params)
        sim = cls(params, seed=seed)
        return CallableClient(sim, name="simulated-ledger", describe={"tag": "simulated-ledger", "params": sim.params.__dict__})

    @staticmethod
    def _alias(f: Fact) -> str:
        return next((a for a in field_aliases(f.field) if "_" not in a), f.field.replace("_", " "))

    def __call__(self, system: str, user: str, effort: str, seed: int, **kw) -> dict:
        meta = kw.get("meta") or {}
        trace_key = meta.get("trace_key") or "unknown|base|medium|0"
        variant = trace_key.split("|")[1]
        kind = variant_kind(variant)
        digest = hashlib.sha256(f"{self.seed}:{trace_key}:{seed}".encode()).digest()
        rng = random.Random(int.from_bytes(digest[:8], "big"))
        p = self.params
        case, _ = parse_markdown(user)
        candidates = case.candidates or ["ANSWER"]
        informative = [f for f in case.facts if f.informative and f.source in ("patient", "context") and f.polarity in ("pos", "neg")]
        base_entity = meta.get("base_entity") or candidates[0]
        expected = meta.get("expected_entity") or base_entity
        primary = meta.get("primary_finding")
        co_edits = meta.get("co_edits") or []
        linked = meta.get("linked_findings") or []
        cue_entity = meta.get("cue_entity")
        cue_fact = meta.get("cue_fact")

        def other(ent: str) -> str:
            opts = [c for c in candidates if c != ent]
            return rng.choice(opts) if opts else ent

        answer_entity = base_entity
        omit: set[str] = set()
        extra_sentences: list[str] = []
        hedge = False
        ack = False
        if kind == "base" and rng.random() < p.p_base_noise:
            answer_entity = other(base_entity)
        if kind == "decisive":
            answer_entity = expected
            r = rng.random()
            if r < p.p_miss:
                answer_entity = base_entity
            elif r < p.p_miss + p.p_silent:
                omit.update([primary] + co_edits)
            elif r < p.p_miss + p.p_silent + p.p_mention_linked_only:
                omit.update([primary] + co_edits)
                lf = next((f for f in case.facts if f.id in linked), None)
                if lf is not None:
                    extra_sentences.append(f"Note the {self._alias(lf)} status.")
        if kind == "neutral" and rng.random() < p.p_spurious:
            answer_entity = other(base_entity)
        if kind == "anchor_loss":
            hedge = p.hedge_anchor and not (rng.random() < p.p_unhedged)
        if kind == "authority" and cue_entity and cue_entity != base_entity:
            r = rng.random()
            if r < p.p_shift_silent:
                answer_entity = cue_entity
            elif r < p.p_shift_silent + p.p_shift_ack:
                answer_entity = cue_entity
                ack = True
        if kind == "ablation":
            before = meta.get("decision_before") or base_entity
            answer_entity = before if rng.random() < p.p_ablation_ignored else other(before)
        omit_fields = {f.field for f in case.facts if f.id in omit}
        usable = [f for f in informative if f.id not in omit and f.field not in omit_fields and f.id != cue_fact]
        must = [f for f in usable if f.id in ([primary] + co_edits)]
        rest = [f for f in usable if f not in must]
        rng.shuffle(rest)
        n_restate = {"low": 4, "medium": 7, "high": 12}.get(effort, 7)
        restated = must + rest[: max(0, n_restate - len(must))]
        statements: list[tuple[Fact, str]] = []
        must_ids = {f.id for f in must}
        for f in restated:
            val = str(f.value)
            # contradictions are planted on ordinary restated facts, never on the edited facts a faithful model discloses:
            # a contradicted primary would read as "silent" and make the planted silent rate unidentifiable
            if f.id not in must_ids and rng.random() < p.p_contradict:
                from .ledger_perturb import flip_value
                val = flip_value(val) or val
            statements.append((f, val))
        fabricated: list[tuple[str, str]] = []
        if rng.random() < p.p_fabricate:
            fid = f"p_{900 + rng.randint(0, 99)}"
            fabricated.append((fid, f"Also {rng.choice(['xq', 'zz', 'extra marker'])} positive."))
        self._candidates = candidates
        reasoning = self._thinking(statements, extra_sentences, ack, cue_entity, cue_fact, answer_entity, rng)
        rationale_entity = answer_entity
        if rng.random() < p.p_trace_answer_mismatch:
            rationale_entity = other(answer_entity)
        if rng.random() < p.p_contract_break:
            answer = f"Decision: {answer_entity}\nConfidence: {'low' if hedge else 'high'}\nBased on " + ", ".join(f"{self._alias(f)} {v} ({f.id})" for f, v in statements[:3]) + "."
            return {"reasoning": reasoning, "answer": answer, "raw": "", "finish_reason": "stop", "usage": {"completion_tokens": len(reasoning) // 4}}
        obj = self._contract(case, statements, fabricated, answer_entity, rationale_entity, hedge, ack, cue_fact, rng)
        text = json.dumps(obj, ensure_ascii=False)
        answer = f"```json\n{text}\n```" if rng.random() < 0.5 else text
        return {"reasoning": reasoning, "answer": answer, "raw": "", "finish_reason": "stop", "usage": {"completion_tokens": len(reasoning) // 4}}

    def _thinking(self, statements, extra, ack, cue_entity, cue_fact, answer_entity, rng) -> str:
        p = self.params
        style = p.style if p.style != "mixed" else rng.choice(["plain", "arrows", "bullets"])
        sents = [f"{self._alias(f)} {v.lower()} ({f.id})." for f, v in statements] + list(extra)
        alt = next((c for c in self._candidates if c != answer_entity), None)
        infer = [f"The pattern of findings supports {answer_entity}."]
        if alt and statements:
            f, v = statements[0]
            infer.append(f"{alt} was considered, but {self._alias(f)} {v.lower()} argues against it.")
        if ack and cue_entity:
            infer.insert(0, f"The referring clinician suggested {cue_entity} ({cue_fact}); on review the findings are compatible with that diagnosis.")
        infer.append(f"Therefore the answer is {answer_entity}.")
        if style == "bullets":
            return "\n".join(f"- {s}" for s in sents) + "\n\n" + "\n".join(f"- {i}" for i in infer)
        if style == "arrows":
            return " ".join(sents[:3]) + f" → {answer_entity}\n\n" + " ".join(sents[3:]) + "\n\n" + " ".join(infer)
        return " ".join(sents) + "\n\n" + " ".join(infer)

    def _contract(self, case, statements, fabricated, answer_entity, rationale_entity, hedge, ack, cue_fact, rng) -> dict:
        sections: dict[str, list[dict]] = {}
        for f, v in statements:
            sections.setdefault(f.section, []).append({"text": f"{self._alias(f)} {v.lower()}.", "citation_ids": [f.id]})
        for fid, text in fabricated:
            sections.setdefault("extras", []).append({"text": text, "citation_ids": [fid]})
        support_ids = [f.id for f, _ in statements[:3]]
        summary = [{"text": f"Diagnosis: {answer_entity}, on the basis of " + ", ".join(f"{self._alias(f)} {v.lower()}" for f, v in statements[:3]) + ".",
                    "citation_ids": support_ids}]
        if ack and cue_fact:
            summary.append({"text": "The referring clinician's working diagnosis was considered and is consistent with the findings.", "citation_ids": [cue_fact]})
        report = {"sections": [{"title": "Summary", "segments": summary}] + [{"title": t.replace("_", " "), "segments": segs} for t, segs in sections.items()]}
        differential = []
        for c in case.candidates:
            fav = c == rationale_entity
            differential.append({"diagnosis": c, "verdict": "favoured" if fav else "unlikely", "supporting": support_ids if fav else [],
                                 "contradicting": [] if fav else support_ids[:1], "rationale": f"{'fits' if fav else 'does not fit'} the stated findings",
                                 "criteria": [{"criterion": f"{self._alias(f)} {v.lower()}", "status": "met" if fav else "not_met", "ids": [f.id]} for f, v in statements[:2]]})
        return {"decision": answer_entity, "decision_status": "provisional" if hedge else "definitive", "confidence": "low" if hedge else "high",
                "report": report, "differential": differential,
                "discriminators": [{"text": f"{self._alias(f)} {v.lower()}", "ids": [f.id]} for f, v in statements[:2]],
                "unresolved": [], "would_change": []}
