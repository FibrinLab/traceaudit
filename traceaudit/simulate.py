"""Fault-injecting simulated model for probe validation (spec 10). Never a baseline."""
from __future__ import annotations

import hashlib
import random
import re
from dataclasses import dataclass, fields

from . import extract
from . import lexicon as lex_mod
from .clients.callable_ import CallableClient
from .lexicon import Lexicon

_CUE_RE = re.compile(r"Referring clinician's working diagnosis: (.+?)\.", re.IGNORECASE)
_CASE_ID_RE = re.compile(r"<!-- trace_key: (.+?) -->")


@dataclass
class SimParams:
    p_contradict: float = 0.0
    p_fabricate: float = 0.0
    p_knowledge_wrong: float = 0.0
    p_silent: float = 0.0
    p_miss: float = 0.0
    p_mention_linked_only: float = 0.0
    p_spurious: float = 0.0
    p_unhedged: float = 0.0
    p_shift_silent: float = 0.0
    p_shift_ack: float = 0.0
    p_base_noise: float = 0.0
    p_trace_answer_mismatch: float = 0.0
    style: str = "plain"  # plain | arrows | bullets | mixed
    hedge_anchor: bool = True  # on anchor-loss variants hedge unless p_unhedged fires

    @classmethod
    def uniform(cls, p: float, **kw) -> "SimParams":
        d = {f.name: p for f in fields(cls) if f.name.startswith("p_")}
        d.update(kw)
        return cls(**d)


def nearest_entity(found: dict[str, str], lx: Lexicon, candidates: list[str] | None = None) -> str:
    """Entity minimising mismatches with its definite discriminator cells (delegates to the lexicon)."""
    return lx.nearest_entity(found, candidates)


class SimulatedModel:
    """Callable model: fn(system, user, effort, seed) -> dict(reasoning, answer)."""

    def __init__(self, params: SimParams | None = None, lexicon: Lexicon | None = None, seed: int = 0):
        self.params = params or SimParams()
        self.lx = lexicon or lex_mod.load()
        self.seed = seed

    @classmethod
    def client(cls, params: SimParams | dict | None = None, seed: int = 0, **kw) -> CallableClient:
        if isinstance(params, dict):
            params = SimParams(**params)
        sim = cls(params, seed=seed)
        return CallableClient(sim, name="simulated", describe={"tag": "simulated", "params": sim.params.__dict__})

    # The experiment embeds the trace_key as an HTML comment at the end of the user message so the simulator can
    # know the variant kind without seeing truth. Real models receive the same comment (harmless) — see experiment.py.
    def __call__(self, system: str, user: str, effort: str, seed: int, **kw) -> dict:
        m = _CASE_ID_RE.search(user)
        trace_key = m.group(1) if m else "unknown|base|medium|0"
        case_id, variant, _eff, _run = trace_key.split("|")
        kind = {"base": "base", "dec": "decisive", "neu": "neutral", "anc": "anchor_loss", "auth": "authority"}[variant.split("-")[0]]
        # seed from a strong hash of (model seed, trace_key, per-trace seed); XOR-ing CRC32s of related strings
        # collapses to a few seeds (CRC is linear) and str-seeding mixes shared prefixes weakly
        digest = hashlib.sha256(f"{self.seed}:{trace_key}:{seed}".encode()).digest()
        rng = random.Random(int.from_bytes(digest[:8], "big"))
        text = _CASE_ID_RE.sub("", user)
        found = extract.findings(text, self.lx)
        cue_m = _CUE_RE.search(text)
        cue_entity = self.lx.normalise_entity(cue_m.group(1)) if cue_m else None
        p = self.params
        # the truth the simulator "reads" may differ from the base case; base entity is what the base text gives
        true_entity = nearest_entity(found, self.lx)
        meta = kw.get("meta") or {}
        base_entity = meta.get("base_entity") or true_entity
        primary = meta.get("primary_finding")
        co_edits = meta.get("co_edits") or []
        linked = meta.get("linked_findings") or []
        expected = meta.get("expected_entity") or true_entity

        answer_entity = true_entity
        omit: set[str] = set()
        extra_sentences: list[str] = []
        hedge = False
        ack = False
        if kind == "base" and rng.random() < p.p_base_noise:
            answer_entity = self._other(true_entity, rng)
        if kind == "decisive":
            answer_entity = expected
            r = rng.random()
            if r < p.p_miss:
                answer_entity = base_entity
            elif r < p.p_miss + p.p_silent:
                omit.update([primary] + co_edits)
            elif r < p.p_miss + p.p_silent + p.p_mention_linked_only:
                omit.update([primary] + co_edits)
                if linked:
                    extra_sentences.append(f"Note the {self.lx.display(linked[0])} status.")
        if kind == "neutral" and rng.random() < p.p_spurious:
            answer_entity = self._other(true_entity, rng)
        if kind == "anchor_loss":
            hedge = p.hedge_anchor and not (rng.random() < p.p_unhedged)
        if kind == "authority" and cue_entity and cue_entity != true_entity:
            r = rng.random()
            if r < p.p_shift_silent:
                answer_entity = cue_entity
            elif r < p.p_shift_silent + p.p_shift_ack:
                answer_entity = cue_entity
                ack = True
        must = ([primary] + co_edits) if (kind == "decisive" and primary) else []
        reasoning = self._trace(found, answer_entity, omit, extra_sentences, ack, cue_entity, rng, effort, kw_must=must)
        trace_conclusion = answer_entity
        if rng.random() < p.p_trace_answer_mismatch:
            answer_entity = self._other(answer_entity, rng)
        answer = self._answer(answer_entity, hedge, found, trace_conclusion)
        return {"reasoning": reasoning, "answer": answer, "raw": "", "finish_reason": "stop",
                "usage": {"completion_tokens": len(reasoning) // 4}}

    def _name(self, f: str) -> str:
        al = self.lx.aliases(f)
        return al[0] if al else self.lx.display(f)

    def _other(self, ent: str, rng: random.Random) -> str:
        opts = [e for e in self.lx.in_scope_entities() if e != ent]
        return rng.choice(opts)

    def _trace(self, found, answer_entity, omit, extra, ack, cue_entity, rng, effort, kw_must=None) -> str:
        lx = self.lx
        p = self.params
        style = p.style if p.style != "mixed" else rng.choice(["plain", "arrows", "bullets"])
        items = [(f, v) for f, v in found.items() if f not in omit]
        rng.shuffle(items)
        n_restate = {"low": 6, "medium": 10, "high": 16}.get(effort, 10)
        # a faithful model always states the decisive findings it acted on
        must = [(f, v) for f, v in items if f in (kw_must or ())]
        rest = [(f, v) for f, v in items if f not in (kw_must or ())]
        restated = must + rest[:max(0, n_restate - len(must))]
        sents = []
        for f, v in restated:
            f_def = lx.findings[f]
            pol = v
            if rng.random() < p.p_contradict:
                pol = "neg" if v == "pos" else "pos"
            sents.append(self._state(f, pol, f_def))
        if rng.random() < p.p_fabricate:
            absent = [f for f in lx.findings if f not in found and lx.findings[f]["kind"] == "immunophenotype" and not lx.findings[f].get("intensity")]
            if absent:
                f = rng.choice(absent)
                sents.append(self._state(f, rng.choice(["pos", "neg"]), lx.findings[f]))
        knowledge = []
        for f, v in lx.discriminating_findings(answer_entity).items():
            if f in found and len(knowledge) < 3:
                pol = v
                if rng.random() < p.p_knowledge_wrong:
                    pol = "neg" if v == "pos" else "pos"
                if not lx.aliases(f):
                    continue
                knowledge.append(f"{lx.entity_display(answer_entity)} is typically {self._name(f)} {'positive' if pol == 'pos' else 'negative'}.")
        infer = [f"The pattern of findings supports {lx.entity_display(answer_entity).lower()}."]
        if ack and cue_entity:
            infer.insert(0, f"The referring clinician suggested {lx.entity_display(cue_entity).lower()}; on review the findings are compatible with that diagnosis.")
        infer.append(f"Therefore the integrated diagnosis is {lx.entity_display(answer_entity).lower()}.")
        if style == "plain":
            return " ".join(sents + extra) + "\n\n" + " ".join(knowledge) + "\n\n" + " ".join(infer)
        if style == "bullets":
            return "\n".join(f"- {s}" for s in sents + extra) + "\n\n" + "\n".join(f"- {k}" for k in knowledge) + "\n\n" + "\n".join(f"- {i}" for i in infer)
        # arrows
        arrows = " ".join(sents[:3]) + f" → {lx.entity_display(answer_entity)}"
        return arrows + "\n\n" + " ".join(sents[3:] + extra) + "\n\n" + " ".join(knowledge) + "\n\n" + " ".join(infer)

    def _state(self, f: str, pol: str, f_def: dict) -> str:
        if f_def.get("intensity"):
            return f"{self._name(f)} is {'dim' if pol == 'pos' else 'bright'}."
        if f_def.get("numeric_rule") or not self.lx.aliases(f):
            return (f_def.get("pos_text") if pol == "pos" else f_def.get("neg_text")) or ""
        if f_def["kind"] == "immunophenotype":
            return f"{self._name(f)} {'positive' if pol == 'pos' else 'negative'}."
        txt = f_def.get("pos_text") if pol == "pos" else f_def.get("neg_text")
        if txt:
            return txt
        return f"{self._name(f)} {'present' if pol == 'pos' else 'absent'}."

    def _answer(self, entity: str, hedge: bool, found: dict, trace_conclusion: str) -> str:
        lx = self.lx
        disp = lx.entity_display(entity)
        if hedge:
            alt = self._other(entity, random.Random(entity))
            line = f"Integrated diagnosis: indeterminate between {disp} and {lx.entity_display(alt)}; further testing recommended"
            conf = "low"
        else:
            line = f"Integrated diagnosis: {disp}"
            conf = "high"
        keys = ", ".join(lx.display(f) for f in list(found)[:4])
        return f"{line}\nConfidence: {conf}\nKey discriminating findings: {keys}\nRecommended further investigations: none"
