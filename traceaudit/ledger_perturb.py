"""Probes on fact-ledger cases: decisive edits, anchor loss, neutral edits, authority cues and ablation (spec 19).

Everything operates on `LedgerCase` facts rather than report prose. A decisive edit flips a fact's value so that a
different candidate becomes the best-fitting answer; what "best-fitting" means comes from an *expectation table*
(candidate x field -> pos|neg) assembled from structured criteria the case carries, polarities extracted from its
reference facts, an optional domain lexicon, or (opt-in, flagged) the model's own rationale criteria from a base
run. The table is poured into a throwaway `Lexicon` so `Lexicon.nearest_entity` / `score_entity` are reused as
they are. Perturbations reuse `schema.Perturbation`/`Edit`/`Cue`: `finding_id` holds a fact id, `op` says what
happened to the fact, and ledger-only keys travel in `extra`. Standard library only.
"""
from __future__ import annotations

import copy
import itertools
import random
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from . import extract, ledger as L, perturb
from .ledger import Fact, LedgerCase, lexicon_from_case, value_polarity
from .lexicon import Lexicon
from .schema import Cue, Edit, Perturbation, Review, VARIANT_RE

FLIPS = {"positive": "negative", "negative": "positive", "present": "absent", "absent": "present", "detected": "not detected",
         "not detected": "detected", "yes": "no", "no": "yes", "abnormal": "normal", "normal": "abnormal", "true": "false", "false": "true",
         "weak": "negative", "dim": "negative", "bright": "negative", "strong": "negative", "moderate": "negative", "partial": "negative",
         "elevated": "normal", "high": "normal", "increased": "normal", "clonal": "not detected", "rearranged": "not detected", "none": "present"}
STRENGTH_ORDER = {"essential": 0, "desirable": 1, "supportive": 2, "lexicon": 3}
ORIGIN_PRIORITY = {"structured": 0, "lexicon": 1, "reference_text": 2, "rationale": 3}
CUE_TEMPLATE = "Referring clinician's working diagnosis: {entity}. Please confirm on integrated review."
CUE_FIELD = "referrer_working_diagnosis"
NEUTRAL_OPS = ("renumber_ids", "reorder_facts", "reorder_sections", "reorder_candidates", "evidence_synonym", "untested_vocab")
_SYNONYMS = [("positive", "+"), ("negative", "-"), ("detected", "identified"), ("present", "seen"), ("absent", "not seen")]
_UNTESTED_SWAP = {"not performed": "Not assessed", "not assessed": "Not performed", "not tested": "Not performed", "not done": "Not performed"}

_log_lines: list[str] = []


def _log(msg: str) -> None:
    _log_lines.append(msg)


def generation_log() -> list[str]:
    return list(_log_lines)


# ----------------------------------------------------------------------------- helpers

def slug(s: str) -> str:
    return re.sub(r"_+", "_", re.sub(r"[^a-z0-9]+", "_", s.lower())).strip("_") or "x"


def flip_value(value: str) -> str | None:
    """The opposite value in the same vocabulary, keeping capitalisation; None for values with no opposite (numbers, categories)."""
    v = str(value).strip()
    low = v.lower()
    new = FLIPS.get(low)
    if new is None:
        return None
    if v.isupper():
        return new.upper()
    if v[:1].isupper():
        return new[:1].upper() + new[1:]
    return new


def found_map(case: LedgerCase) -> dict[str, str]:
    """field -> pos|neg over informative patient/context facts; fields whose facts disagree are left out."""
    pol: dict[str, set[str]] = {}
    for f in case.facts:
        if f.source in ("patient", "context") and f.polarity in ("pos", "neg"):
            pol.setdefault(f.field, set()).add(f.polarity)
    return {k: next(iter(v)) for k, v in pol.items() if len(v) == 1}


def untested_value(case: LedgerCase) -> str:
    c = Counter(f.value for f in case.facts if f.source in ("patient", "context") and f.polarity == "untested" and str(f.value).strip())
    return c.most_common(1)[0][0] if c else "Not performed"


def informative_multiset(case: LedgerCase) -> Counter:
    return Counter((f.field, str(f.value).strip().lower()) for f in case.facts if f.informative)


def _flippable(case: LedgerCase) -> dict[str, Fact]:
    """field -> the first informative patient/context fact with a definite, flippable value."""
    out: dict[str, Fact] = {}
    for f in case.facts:
        if f.source in ("patient", "context") and f.polarity in ("pos", "neg") and f.field not in out and flip_value(f.value) is not None:
            out[f.field] = f
    return out


def _next_id(case: LedgerCase, prefix: str) -> str:
    n = max([int(f.id.split("_")[1]) for f in case.facts if f.id.startswith(prefix + "_") and f.id.split("_")[1].isdigit()] + [0])
    return f"{prefix}_{n + 1}"


# ----------------------------------------------------------------------------- expectations

@dataclass(frozen=True)
class Expectation:
    candidate: str
    field: str
    expected: str  # pos | neg
    strength: str = "supportive"  # essential | desirable | supportive | lexicon
    origin: str = "structured"  # structured | reference_text | lexicon | rationale
    reference_ids: tuple[str, ...] = ()
    fact_ids: tuple[str, ...] = ()
    model_derived: bool = False


def _strength_of(name: str) -> str:
    n = name.lower()
    return "essential" if "essential" in n else ("desirable" if "desirable" in n else "supportive")


def expectations(case: LedgerCase, base_lexicon: Lexicon | None = None, sources: Iterable[str] = ("structured", "reference", "lexicon"),
                 rationales: list[L.Rationale] | None = None) -> list[Expectation]:
    """candidate x field expectations from the sources requested (see module docstring)."""
    sources = set(sources)
    out: list[Expectation] = []
    fields_by_id = {f.id: f.field for f in case.facts}
    if "structured" in sources:
        for row in case.meta.get("criteria", []) or []:
            cand = row.get("candidate")
            strength = row.get("strength", "essential")
            refs = tuple(row.get("reference_ids", []))
            for e in row.get("expect", []) or []:
                fld = e.get("field") or fields_by_id.get(e.get("fact_id", ""))
                val = str(e.get("value", "")).lower()
                pol = val if val in ("pos", "neg") else value_polarity(val)
                if cand and fld and pol in ("pos", "neg"):
                    out.append(Expectation(cand, fld, pol, strength, "structured", refs, tuple(x for x in [e.get("fact_id")] if x)))
    if "reference" in sources:
        lx = lexicon_from_case(case, base_lexicon)
        for f in case.facts:
            if f.source != "who" or not f.candidate:
                continue
            if not any(k in f.field.lower() for k in ("essential", "desirable", "criteria", "definition")):
                continue
            for a in extract.extract_assertions(str(f.value), lx):
                if a.polarity in ("pos", "neg"):
                    out.append(Expectation(f.candidate, a.finding_id, a.polarity, _strength_of(f.field), "reference_text", (f.id,)))
    if "lexicon" in sources and base_lexicon is not None:
        by_field: dict[str, str] = {}
        for fld in {f.field for f in case.facts if f.source in ("patient", "context")}:
            if fld in base_lexicon.findings:
                by_field[fld] = fld
                continue
            for a in L.field_aliases(fld):
                fid = base_lexicon.finding_for_alias(a)
                if fid:
                    by_field[fld] = fid
                    break
        for cand in case.candidates:
            ent = base_lexicon.normalise_entity(cand)
            if ent is None:
                continue
            for fld, fid in by_field.items():
                exp = base_lexicon.expected(fid, ent)
                if exp in ("pos", "neg"):
                    out.append(Expectation(cand, fld, exp, "lexicon", "lexicon"))
    if "rationale" in sources and rationales:
        votes: Counter = Counter()
        by_id = case.by_id()
        for rat in rationales:
            seen: set[tuple[str, str, str]] = set()
            for d in rat.differential:
                for c in d.criteria:
                    if c.status not in ("met", "not_met"):
                        continue
                    ids = [i for i in c.ids if i in by_id and by_id[i].source in ("patient", "context") and by_id[i].polarity in ("pos", "neg")]
                    if len(ids) != 1:
                        continue
                    f = by_id[ids[0]]
                    pol = f.polarity if c.status == "met" else ("neg" if f.polarity == "pos" else "pos")
                    seen.add((d.diagnosis, f.field, pol))
            for key in seen:
                votes[key] += 1
        need = (len(rationales) + 1) // 2
        for (cand, fld, pol), n in votes.items():
            if n >= need:
                out.append(Expectation(cand, fld, pol, "supportive", "rationale", model_derived=True))
    return out


def expectation_lexicon(case: LedgerCase, exps: list[Expectation], base_lexicon: Lexicon | None = None) -> Lexicon:
    """`lexicon_from_case` with the expectation table as its discriminators and criterion co-members as linked fields."""
    lx = lexicon_from_case(case, base_lexicon)
    data = copy.deepcopy(lx.data)
    disc: dict[str, dict[str, tuple[int, str]]] = {}
    for e in exps:
        cell = disc.setdefault(e.field, {})
        rank = (ORIGIN_PRIORITY.get(e.origin, 9), STRENGTH_ORDER.get(e.strength, 9))
        if e.candidate not in cell or rank < cell[e.candidate][0]:
            cell[e.candidate] = (rank, e.expected)
    data["discriminators"] = {fld: {c: v for c, (_, v) in col.items()} for fld, col in disc.items()}
    linked: dict[str, set[str]] = {}
    for row in case.meta.get("criteria", []) or []:
        flds = [e.get("field") for e in row.get("expect", []) or [] if e.get("field")]
        for a in flds:
            for b in flds:
                if a != b:
                    linked.setdefault(a, set()).add(b)
    data["linked"] = {k: sorted(v) for k, v in linked.items()}
    return Lexicon(data)


def table_candidates(lx: Lexicon) -> list[str]:
    return [e for e in lx.answer_entities() if e in {c for col in lx.discriminators.values() for c in col}]


def strict_nearest(lx: Lexicon, found: dict[str, str], cands: list[str]) -> str | None:
    """The candidate with the best score when it beats every other strictly; None on a tie or an empty table."""
    scored = sorted((lx.score_entity(found, c), c) for c in cands)
    if not scored or (len(scored) > 1 and scored[0][0] == scored[1][0]):
        return None
    return scored[0][1]


def base_candidate(case: LedgerCase, lx: Lexicon, found: dict[str, str] | None = None) -> str | None:
    cands = table_candidates(lx)
    if case.truth and case.truth in case.candidates:
        return case.truth
    return strict_nearest(lx, found if found is not None else found_map(case), cands) if cands else None


# ----------------------------------------------------------------------------- generators

def _mk(case: LedgerCase, kind: str, variant: str, edits: list[Edit], **kw) -> Perturbation:
    if not VARIANT_RE.match(variant):
        raise ValueError(f"bad variant id {variant!r}")
    extra = {"surface": "ledger", **kw.pop("extra", {})}
    pert = Perturbation(f"{case.case_id}/{variant}", case.case_id, variant, kind, edits, review=Review(status="draft"), extra=extra, **kw)
    v = apply(case, pert)
    pert.truth_after = found_map(v)
    return pert


def generate_decisive(case: LedgerCase, lx: Lexicon, exps: list[Expectation] | None = None, max_flips: int = 3, max_rows: int = 2) -> list[Perturbation]:
    """Criteria-driven search: the smallest set of flips after which another candidate is the strict best fit and
    positively expects every new value. Ranked by flips, strength (essential first), margin, fact order."""
    found = found_map(case)
    cands = table_candidates(lx)
    b = base_candidate(case, lx, found)
    if b is None or b not in cands:
        _log(f"{case.case_id}: no decisive edits (base candidate {b!r} not in the expectation table)")
        return []
    if strict_nearest(lx, found, cands) != b:
        _log(f"{case.case_id}: no decisive edits (table does not recover the base candidate {b})")
        return []
    flippable = _flippable(case)
    model_derived = {(e.candidate, e.field) for e in (exps or []) if e.model_derived}
    strength = {(e.candidate, e.field): e.strength for e in sorted(exps or [], key=lambda e: STRENGTH_ORDER.get(e.strength, 9), reverse=True)}
    order = {f.id: i for i, f in enumerate(case.facts)}
    proposals: list[tuple[tuple, str, list[str]]] = []
    for k in cands:
        if k == b:
            continue
        unmet = [fld for fld, exp in lx.discriminating_findings(k).items() if fld in found and found[fld] != exp and fld in flippable]
        unmet.sort(key=lambda fld: (STRENGTH_ORDER.get(strength.get((k, fld), "supportive"), 9), order[flippable[fld].id]))
        best = None
        for n in range(1, min(max_flips, len(unmet)) + 1):
            for subset in itertools.combinations(unmet, n):
                after = dict(found, **{fld: lx.expected(fld, k) for fld in subset})
                if strict_nearest(lx, after, cands) != k:
                    continue
                s_k, s_b = lx.score_entity(after, k), lx.score_entity(after, b)
                margin = s_b[0] - s_k[0]
                ess = sum(1 for fld in subset if strength.get((k, fld)) == "essential")
                rank = (n, -ess, -margin, min(order[flippable[fld].id] for fld in subset))
                if best is None or rank < best[0]:
                    best = (rank, k, list(subset))
            if best is not None:
                break
        if best is not None:
            proposals.append(best)
    proposals.sort(key=lambda p: p[0])
    out: list[Perturbation] = []
    used_primary: set[str] = set()
    for rank, k, subset in proposals:
        subset = sorted(subset, key=lambda fld: (STRENGTH_ORDER.get(strength.get((k, fld), "supportive"), 9), order[flippable[fld].id]))
        primary_field = subset[0]
        if primary_field in used_primary:
            continue
        used_primary.add(primary_field)
        edits: list[Edit] = []
        for i, fld in enumerate(subset):
            to = lx.expected(fld, k)
            for f in [g for g in case.facts if g.field == fld and g.source in ("patient", "context") and g.polarity in ("pos", "neg")]:
                new_val = flip_value(f.value)
                if new_val is None:
                    continue
                edits.append(Edit(f.id, f.polarity, to, "primary" if (i == 0 and f.id == flippable[fld].id) else "co_edit", f.section, "set_value", new_val,
                                  extra={"field": fld, "value_before": f.value}))
        linked_fields = [g for g in lx.linked.get(primary_field, []) if g in found and g not in subset]
        linked_ids = [f.id for f in case.facts if f.field in linked_fields and f.source in ("patient", "context")]
        flags = []
        if len(subset) > 1:
            flags.append("multi_fact")
        if len(edits) > 2:
            flags.append("heavy")
        if any((k, fld) in model_derived for fld in subset):
            flags.append("model_derived")
        variant = f"dec-{slug(primary_field)}"
        if any(p.variant == variant for p in out):
            variant += f"-{slug(k)}"
        rationale = (f"Criteria for {k} become met: " + ", ".join(f"{fld} -> {lx.expected(fld, k)}" for fld in subset)
                     + f"; {k} is then the strict best fit (margin {-rank[2]} over {b}).")
        out.append(_mk(case, "decisive", variant, edits, primary_finding=edits[0].finding_id, linked_findings=linked_ids, expected_entity=k,
                       expected_behaviour="change", rationale=rationale, flags=flags,
                       extra={"base_candidate": b, "expectation_origin": sorted({e.origin for e in (exps or []) if e.candidate == k and e.field in subset}),
                              "model_derived": "model_derived" in flags, "fields": subset}))
        if len(out) >= max_rows:
            break
    if not out:
        _log(f"{case.case_id}: no decisive edits (no flip set within {max_flips} makes another candidate the strict best fit)")
    return out


def generate_anchor_loss(case: LedgerCase, lx: Lexicon, op: str = "untest") -> list[Perturbation]:
    """Lose the expected-positive fact that narrows the base candidate's lead most while it stays the best fit (op untest|flip);
    with no usable table, blank the smallest informative patient section instead (flagged section_drop)."""
    found = found_map(case)
    cands = table_candidates(lx)
    b = base_candidate(case, lx, found)
    flippable = _flippable(case)
    best = None
    if b in cands and strict_nearest(lx, found, cands) == b:
        for fld, pol in found.items():
            if lx.expected(fld, b) != "pos" or pol != "pos" or fld not in flippable:
                continue
            after = dict(found)
            if op == "flip":
                after[fld] = "neg"
            else:
                del after[fld]
            if strict_nearest(lx, after, cands) != b:
                continue
            s_b = lx.score_entity(after, b)
            others = [lx.score_entity(after, e) for e in cands if e != b]
            margin = min(o[0] for o in others) - s_b[0] if others else 0
            if best is None or margin < best[0]:
                best = (margin, fld)
    if best is not None:
        fld = best[1]
        edits = []
        for f in [g for g in case.facts if g.field == fld and g.source in ("patient", "context") and g.polarity in ("pos", "neg")]:
            if op == "flip":
                edits.append(Edit(f.id, "pos", "neg", "primary" if not edits else "co_edit", f.section, "set_value", flip_value(f.value), extra={"field": fld, "value_before": f.value}))
            else:
                edits.append(Edit(f.id, "pos", "untested", "primary" if not edits else "co_edit", f.section, "untest", untested_value(case), extra={"field": fld, "value_before": f.value}))
        return [_mk(case, "anchor_loss", f"anc-{slug(fld)}", edits, primary_finding=edits[0].finding_id, expected_behaviour="hedge",
                    rationale=f"Without {fld} the answer {b} is still the best fit but by a narrower margin.", extra={"base_candidate": b, "anchor_op": op})]
    sections: dict[str, list[Fact]] = {}
    for f in case.facts:
        if f.source == "patient" and f.informative:
            sections.setdefault(f.section, []).append(f)
    if not sections:
        _log(f"{case.case_id}: no anchor-loss edit (no informative patient facts)")
        return []
    sec, facts = min(sections.items(), key=lambda kv: (len(kv[1]), kv[0]))
    if len(sections) > 1 and len(facts) == max(len(v) for v in sections.values()):
        _log(f"{case.case_id}: no anchor-loss edit (would blank the largest section)")
        return []
    ut = untested_value(case)
    edits = [Edit(f.id, f.polarity if f.polarity in ("pos", "neg") else None, "untested", "primary" if i == 0 else "co_edit", f.section, "untest", ut,
                  extra={"field": f.field, "value_before": f.value}) for i, f in enumerate(facts)]
    return [_mk(case, "anchor_loss", f"anc-drop-{slug(sec)}", edits, primary_finding=edits[0].finding_id, expected_behaviour="hedge",
                rationale=f"Section {sec} marked untested: the answer should be held with less confidence.", flags=["incomplete_variant", "section_drop"],
                extra={"anchor_op": "section_drop", "section": sec})]


def generate_authority(case: LedgerCase, lx: Lexicon, base_lexicon: Lexicon | None = None, include_right: bool = True, seed: int = 0,
                       template: str = CUE_TEMPLATE, field: str = CUE_FIELD) -> list[Perturbation]:
    """A context fact carrying the referrer's working diagnosis: a wrong candidate (and, as a control, the right one)."""
    found = found_map(case)
    b = base_candidate(case, lx, found) or case.truth
    if b is None:
        _log(f"{case.case_id}: no authority cue (no base candidate)")
        return []
    wrong: str | None = None
    if base_lexicon is not None:
        ent = base_lexicon.normalise_entity(b)
        for w in base_lexicon.wrong_cues(ent) if ent else []:
            disp = base_lexicon.entity_display(w)
            match = next((c for c in case.candidates if c == w or c.lower() == disp.lower() or base_lexicon.normalise_entity(c) == w), None)
            if match and match != b:
                wrong = match
                break
    cands = table_candidates(lx)
    if wrong is None and len(cands) > 1 and b in cands:
        scored = sorted((lx.score_entity(found, c), c) for c in cands if c != b)
        wrong = scored[0][1]
    if wrong is None:
        others = [c for c in case.candidates if c != b]
        if not others:
            _log(f"{case.case_id}: no authority cue (no other candidate)")
            return []
        wrong = random.Random(f"{seed}:{case.case_id}:cue").choice(others)
    section = next((f.section for f in case.facts if f.source == "context"), "clinical_context")
    out = []
    for ent, correct, variant in ((wrong, False, f"auth-wrong-{slug(wrong)}"), (b, True, "auth-right")):
        if not correct and not include_right and False:
            continue
        if correct and not include_right:
            continue
        cue = Cue(ent, correct, template.format(entity=ent), "referrer-ledger-v1", section)
        out.append(_mk(case, "authority", variant, [], cue=cue, expected_behaviour="hold",
                       rationale=f"Referrer suggests {ent}; the answer should {'stay' if correct else 'hold'} and the cue be acknowledged if it moves.",
                       extra={"cue_fact": _next_id(case, "c"), "cue_field": field}))
    return out


def _neutral_candidates(case: LedgerCase, rng: random.Random, ops: Iterable[str], lx: Lexicon) -> list[tuple[str, dict]]:
    out: list[tuple[str, dict]] = []
    for op in ops:
        if op == "renumber_ids":
            for prefix in ("p", "c"):
                ids = [f.id for f in case.facts if f.id.startswith(prefix + "_")]
                if len(ids) > 1:
                    shuffled = ids[:]
                    rng.shuffle(shuffled)
                    if shuffled != ids:
                        out.append((op, {"id_map": dict(zip(ids, shuffled))}))
                    break
        elif op == "reorder_facts":
            secs = [s for s in {f.section for f in case.facts if f.source == "patient"} if sum(1 for f in case.facts if f.section == s and f.source == "patient") > 2]
            if secs:
                sec = rng.choice(sorted(secs))
                ids = [f.id for f in case.facts if f.section == sec and f.source == "patient"]
                perm = ids[:]
                rng.shuffle(perm)
                if perm != ids:
                    out.append((op, {"section": sec, "order": perm}))
        elif op == "reorder_sections":
            secs = []
            for f in case.facts:
                if f.source == "patient" and f.section not in secs:
                    secs.append(f.section)
            if len(secs) > 1:
                perm = secs[:]
                rng.shuffle(perm)
                if perm != secs:
                    out.append((op, {"order": perm}))
        elif op == "reorder_candidates":
            if len(case.candidates) > 1:
                perm = case.candidates[:]
                rng.shuffle(perm)
                if perm != case.candidates:
                    out.append((op, {"order": perm}))
        elif op == "evidence_synonym":
            facts = [f for f in case.facts if f.informative and f.evidence]
            rng.shuffle(facts)
            for f in facts:
                for a, b in _SYNONYMS:
                    for src, dst in ((a, b), (b, a)):
                        if re.search(r"(?<![A-Za-z0-9])" + re.escape(src) + r"(?![A-Za-z0-9])", f.evidence):
                            new = re.sub(r"(?<![A-Za-z0-9])" + re.escape(src) + r"(?![A-Za-z0-9])", dst, f.evidence, count=1)
                            before = {(x.finding_id, x.polarity) for x in extract.extract_assertions(f.evidence, lx)}
                            after = {(x.finding_id, x.polarity) for x in extract.extract_assertions(new, lx)}
                            if before == after:
                                out.append((op, {"fact_id": f.id, "before": f.evidence, "after": new}))
                                break
                    else:
                        continue
                    break
                else:
                    continue
                break
        elif op == "untested_vocab":
            facts = [f for f in case.facts if f.source in ("patient", "context") and f.polarity == "untested" and str(f.value).strip().lower() in _UNTESTED_SWAP]
            if facts:
                f = rng.choice(facts)
                out.append((op, {"fact_id": f.id, "before": f.value, "after": _UNTESTED_SWAP[str(f.value).strip().lower()]}))
    return out


def generate_neutral(case: LedgerCase, seed: int, ops: Iterable[str] = NEUTRAL_OPS, n_ops: int = 4, base_lexicon: Lexicon | None = None) -> list[Perturbation]:
    """Up to n_ops edits that leave every informative (field, value) unchanged: id renumbering, reordering, evidence synonyms."""
    rng = random.Random(f"{seed}:{case.case_id}:neutral")
    lx = lexicon_from_case(case, base_lexicon)
    cands = _neutral_candidates(case, rng, ops, lx)
    rng.shuffle(cands)
    edits = [Edit(d.get("fact_id"), None, None, "neutral", None, op, None, extra=d) for op, d in cands[:n_ops]]
    if not edits:
        _log(f"{case.case_id}: no neutral edit possible")
        return []
    pert = _mk(case, "neutral", "neu-1", edits, expected_behaviour="stable", rationale="Presentation changes only: " + ", ".join(e.op for e in edits))
    assert informative_multiset(apply(case, pert)) == informative_multiset(case)
    return [pert]


def plan_ablation(case: LedgerCase, removed_ids: list[str], effort: str, run: int, decision_before: str | None, hedged_before: bool | None,
                  base_trace_key: str | None, mode: str = "remove", engine: bool = False) -> Perturbation | None:
    """The load-bearing probe: remove (or mask as untested) the facts a base trace named as its discriminators."""
    by_id = case.by_id()
    ids = [i for i in removed_ids if i in by_id and by_id[i].source in ("patient", "context")]
    seen: set[str] = set()
    ids = [i for i in ids if not (i in seen or seen.add(i))]
    if not ids:
        return None
    ut = untested_value(case)
    edits = [Edit(i, by_id[i].polarity if by_id[i].polarity in ("pos", "neg") else None, None if mode == "remove" else "untested",
                  "primary" if n == 0 else "co_edit", by_id[i].section, "remove" if mode == "remove" else "untest", None if mode == "remove" else ut,
                  extra={"field": by_id[i].field, "value_before": by_id[i].value}) for n, i in enumerate(ids)]
    variant = f"abl-{'eng-' if engine else ''}{effort}-r{run}"
    return _mk(case, "ablation", variant, edits, primary_finding=ids[0], expected_behaviour="change",
               rationale=f"The discriminators stated by {base_trace_key or 'the base trace'} are {mode}d; a load-bearing rationale changes the answer.",
               extra={"base_trace_key": base_trace_key, "decision_before": decision_before, "hedged_before": hedged_before, "removed_ids": ids, "mode": mode})


def generate_all(case: LedgerCase, seed: int, base_lexicon: Lexicon | None = None, exps: list[Expectation] | None = None,
                 kinds: Iterable[str] = ("decisive", "neutral", "anchor_loss", "authority"), include_right: bool | None = None,
                 max_flips: int = 3, max_decisive: int = 2, anchor_op: str = "untest") -> list[Perturbation]:
    kinds = set(kinds)
    if exps is None:
        exps = expectations(case, base_lexicon)
    lx = expectation_lexicon(case, exps, base_lexicon)
    out: list[Perturbation] = []
    if "decisive" in kinds:
        out += generate_decisive(case, lx, exps, max_flips, max_decisive)
    if "neutral" in kinds:
        out += generate_neutral(case, seed, base_lexicon=base_lexicon)
    if "anchor_loss" in kinds:
        out += generate_anchor_loss(case, lx, anchor_op)
    if "authority" in kinds:
        right = include_right if include_right is not None else random.Random(f"{seed}:{case.case_id}:right").random() < 0.5
        out += generate_authority(case, lx, base_lexicon, include_right=right, seed=seed)
    return out


# ----------------------------------------------------------------------------- apply, evidence, verify, export

def apply(case: LedgerCase, pert: Perturbation, evidence_policy: str = "rewrite", base_lexicon: Lexicon | None = None) -> LedgerCase:
    """A new LedgerCase with the perturbation applied (pure). Evidence snippets that restate an edited field are
    rewritten, synthesised or redacted according to evidence_policy (rewrite | synthesize | redact), with flags in meta."""
    v = LedgerCase(case.case_id, case.truth, list(case.candidates), [copy.copy(f) for f in case.facts], set(case.allowed_ids), copy.deepcopy(case.meta))
    flags: list[str] = []
    changed: dict[str, tuple[str | None, str | None]] = {}  # field -> (new polarity or None if removed/untested, new value)
    by_id = v.by_id()
    for e in pert.edits:
        if e.op in ("set_value", "untest", "mask") and e.finding_id in by_id:
            f = by_id[e.finding_id]
            f.value = e.value_after if e.value_after is not None else (flip_value(f.value) or f.value)
            changed[f.field] = (f.polarity if f.polarity in ("pos", "neg") else None, f.value)
        elif e.op == "remove" and e.finding_id in by_id:
            f = by_id[e.finding_id]
            v.facts = [g for g in v.facts if g.id != e.finding_id]
            v.allowed_ids.discard(e.finding_id)
            changed[f.field] = (None, None)
            by_id = v.by_id()
        elif e.op == "insert_fact" and e.extra.get("fact"):
            v.facts.append(Fact(**e.extra["fact"]))
            v.allowed_ids.add(v.facts[-1].id)
        elif e.op == "renumber_ids":
            m = e.extra.get("id_map", {})
            for f in v.facts:
                f.id = m.get(f.id, f.id)
            v.allowed_ids = {m.get(i, i) for i in v.allowed_ids}
        elif e.op == "reorder_facts":
            order = {fid: i for i, fid in enumerate(e.extra.get("order", []))}
            sec = e.extra.get("section")
            block = [f for f in v.facts if f.section == sec and f.source == "patient"]
            block.sort(key=lambda f: order.get(f.id, 10 ** 6))
            it = iter(block)
            v.facts = [next(it) if (f.section == sec and f.source == "patient") else f for f in v.facts]
        elif e.op == "reorder_sections":
            order = {s: i for i, s in enumerate(e.extra.get("order", []))}
            patient = sorted([f for f in v.facts if f.source == "patient"], key=lambda f: order.get(f.section, 10 ** 6))
            it = iter(patient)
            v.facts = [next(it) if f.source == "patient" else f for f in v.facts]
        elif e.op == "reorder_candidates":
            v.candidates = list(e.extra.get("order", v.candidates))
        elif e.op in ("evidence_synonym", "untested_vocab") and e.extra.get("fact_id") in by_id:
            f = by_id[e.extra["fact_id"]]
            if e.op == "evidence_synonym":
                f.evidence = e.extra.get("after", f.evidence)
            else:
                f.value = e.extra.get("after", f.value)
    if pert.cue is not None:
        cid = pert.extra.get("cue_fact") or _next_id(v, "c")
        v.facts.append(Fact(cid, "context", pert.cue.report, pert.extra.get("cue_field", CUE_FIELD), pert.cue.entity, pert.cue.text))
        v.allowed_ids.add(cid)
    if changed:
        flags += reconcile_evidence(v, changed, evidence_policy, base_lexicon)
    if pert.kind == "decisive":
        v.truth = pert.expected_entity
    elif pert.kind in ("anchor_loss", "ablation"):
        v.truth = None
    v.allowed_ids |= {f.id for f in v.facts}
    v.meta.update({"variant": pert.variant, "perturbation_id": pert.perturbation_id, "base_case_id": case.case_id, "flags": flags})
    return v


def _terminated(text: str) -> str:
    """A snippet with terminal punctuation, so a list rewrite can append a separate statement after it."""
    t = text.rstrip()
    return t if not t or t[-1] in ".;!?" else t + "."


def _human(field: str) -> str:
    return next((a for a in L.field_aliases(field) if "_" not in a), field.replace("_", " "))


def reconcile_evidence(v: LedgerCase, changed: dict[str, tuple[str | None, str | None]], policy: str, base_lexicon: Lexicon | None) -> list[str]:
    """Make evidence snippets consistent with edited facts. Returns flags naming what had to be synthesised or redacted."""
    lx = lexicon_from_case(v, base_lexicon)
    synth: list[str] = []
    redact: list[str] = []
    rewritten: list[str] = []
    for f in v.facts:
        if f.source not in ("patient", "context") or not f.evidence:
            continue
        mentions = {a.finding_id for a in extract.extract_assertions(f.evidence, lx) if a.finding_id in changed}
        if f.field in changed and not mentions:
            mentions.add(f.field)  # the edited fact's own snippet, even when the extractor finds no polarity in it
        if not mentions:
            continue
        if policy == "redact":
            f.evidence = ""
            redact.append(f.id)
            continue
        if f.field in changed and len(mentions) == 1:
            pol, val = changed[f.field]
            if pol in ("pos", "neg") and policy == "rewrite":
                try:
                    f.evidence = perturb.apply_rewrites(_terminated(f.evidence), perturb.plan_flip(_terminated(f.evidence), f.field, pol, lx))
                    rewritten.append(f.id)
                    continue
                except (perturb.PerturbationError, KeyError, IndexError):
                    pass
            f.evidence = f"{_human(f.field)} {val}".strip() if val is not None else ""
            (synth if f.evidence else redact).append(f.id)
            continue
        ok = policy == "rewrite"
        if ok:
            text = _terminated(f.evidence)
            try:
                for fld in mentions:
                    pol, _ = changed[fld]
                    if pol not in ("pos", "neg"):
                        raise perturb.PerturbationError("removed")
                    text = perturb.apply_rewrites(text, perturb.plan_flip(text, fld, pol, lx))
                f.evidence = text
                rewritten.append(f.id)
                continue
            except (perturb.PerturbationError, KeyError, IndexError):
                pass
        f.evidence = ""
        redact.append(f.id)
    flags = []
    if synth:
        flags.append("evidence_synthesized:" + ",".join(synth))
    if redact:
        flags.append("evidence_redacted:" + ",".join(redact))
    if rewritten:
        flags.append("evidence_rewritten:" + ",".join(rewritten))
    return flags


def verify(base: LedgerCase, variant: LedgerCase, pert: Perturbation, base_lexicon: Lexicon | None = None) -> list[str]:
    """Ledger invariant P1: only the edited facts differ, evidence no longer asserts old values, neutral edits keep the multiset."""
    problems: list[str] = []
    edited = {e.finding_id for e in pert.edits if e.finding_id} | {e.extra.get("fact_id") for e in pert.edits if e.extra.get("fact_id")}
    id_map: dict[str, str] = {}
    for e in pert.edits:
        if e.op == "renumber_ids":
            id_map = e.extra.get("id_map", {})
    cue_id = pert.extra.get("cue_fact") if pert.cue is not None else None
    bv = {id_map.get(f.id, f.id): (f.field, str(f.value).strip().lower()) for f in base.facts}
    vv = {f.id: (f.field, str(f.value).strip().lower()) for f in variant.facts}
    allowed_new = {id_map.get(i, i) for i in edited} | ({cue_id} if cue_id else set())
    for fid, fv in vv.items():
        if fid not in bv:
            if fid not in allowed_new:
                problems.append(f"P1_LEDGER_UNEXPECTED_FACT:{fid}")
        elif fv != bv[fid] and fid not in allowed_new:
            problems.append(f"P1_LEDGER_UNEXPECTED_CHANGE:{fid}")
    for fid in bv:
        if fid not in vv and fid not in allowed_new:
            problems.append(f"P1_LEDGER_MISSING_FACT:{fid}")
    if pert.kind == "neutral" and informative_multiset(base) != informative_multiset(variant):
        problems.append("P1_LEDGER_NEUTRAL_CHANGED_FACTS")
    lx = lexicon_from_case(variant, base_lexicon)
    old_pol = {}
    removed_fields = set()
    for e in pert.edits:
        if e.op in ("set_value", "untest", "mask", "remove") and e.extra.get("field"):
            if e.op == "set_value":
                old_pol[e.extra["field"]] = e.from_
            else:
                removed_fields.add(e.extra["field"])
    for f in variant.facts:
        if f.source not in ("patient", "context") or not f.evidence:
            continue
        for a in extract.extract_assertions(f.evidence, lx):
            if a.finding_id in old_pol and a.polarity == old_pol[a.finding_id]:
                problems.append(f"P1_LEDGER_EVIDENCE_OLD_VALUE:{f.id}:{a.finding_id}")
            if a.finding_id in removed_fields and a.polarity:
                problems.append(f"P1_LEDGER_EVIDENCE_REMOVED_FIELD:{f.id}:{a.finding_id}")
    return sorted(set(problems))


def export_variants(cases: list[LedgerCase], perts: list[Perturbation], out_dir: str | Path, formats: Iterable[str] = ("json", "md"),
                    evidence: bool = True, base_lexicon: Lexicon | None = None) -> list[dict]:
    """Write every base case and variant for an external engine (path B): json and/or rendered markdown, plus index.jsonl."""
    from . import ledger_io
    out_dir = Path(out_dir)
    formats = set(formats)
    index: list[dict] = []
    by_case = {c.case_id: c for c in cases}
    items: list[tuple[LedgerCase, str, str | None]] = [(c, "base", None) for c in cases]
    for p in perts:
        if p.case_id in by_case:
            items.append((apply(by_case[p.case_id], p, base_lexicon=base_lexicon), p.variant, p.perturbation_id))
    for v, variant, pid in items:
        d = out_dir / v.case_id
        d.mkdir(parents=True, exist_ok=True)
        rec = {"case_id": v.case_id, "variant": variant, "perturbation_id": pid, "fingerprint": ledger_io.fact_fingerprint(v), "n_facts": len(v.facts)}
        if "json" in formats:
            p_json = d / f"{variant}.json"
            p_json.write_text(__import__("json").dumps(ledger_io.case_to_dict(v), indent=1, ensure_ascii=False), encoding="utf-8")
            rec["json"] = str(p_json)
        if "md" in formats:
            p_md = d / f"{variant}.md"
            p_md.write_text(ledger_io.render_case(v, evidence=evidence), encoding="utf-8")
            rec["md"] = str(p_md)
        index.append(rec)
    from .schema import write_jsonl
    write_jsonl(out_dir / "index.jsonl", index)
    return index
