"""Perturbation generation and application (spec 05)."""
from __future__ import annotations

import random
import re
from dataclasses import dataclass

from . import extract
from . import lexicon as lex_mod
from .lexicon import Lexicon
from .schema import Case, Cue, Edit, Perturbation, Review
from .textutil import split_sentences


class PerturbationError(ValueError):
    pass


# ----------------------------------------------------------------------------- catalogues [DRAFT-CLINICAL]

@dataclass(frozen=True)
class DecisiveRow:
    base: str
    target: str
    primary: tuple[str, str, str]          # finding, from, to
    co_edits: tuple[tuple[str, str, str], ...]
    preconditions: tuple[tuple[str, str], ...] = ()   # finding must have this truth value (or be absent) in base
    flags: tuple[str, ...] = ()
    subtypes: tuple[str, ...] = ()           # restrict to subtypes when non-empty
    rationale: str = ""


def decisive_catalogue(lx: Lexicon) -> tuple[DecisiveRow, ...]:
    """Decisive rows authored in the lexicon (`perturbations.decisive`). Empty when the domain has none."""
    rows = []
    for r in lx.perturbation_catalogue().get("decisive", []):
        rows.append(DecisiveRow(r["base"], r["target"], tuple(r["primary"]), tuple(tuple(c) for c in r.get("co_edits", [])),
                                tuple(tuple(c) for c in r.get("preconditions", [])), tuple(r.get("flags", [])), tuple(r.get("subtypes", [])),
                                r.get("rationale", "")))
    return tuple(rows)


@dataclass(frozen=True)
class AnchorRow:
    base: str
    primary: tuple[str, str, str]
    co_edits: tuple[tuple[str, str, str], ...]
    subtypes: tuple[str, ...] = ()
    rationale: str = ""


def anchor_catalogue(lx: Lexicon) -> tuple[AnchorRow, ...]:
    rows = []
    for r in lx.perturbation_catalogue().get("anchor_loss", []):
        rows.append(AnchorRow(r["base"], tuple(r["primary"]), tuple(tuple(c) for c in r.get("co_edits", [])), tuple(r.get("subtypes", [])), r.get("rationale", "")))
    return tuple(rows)


def _flip(pol: str) -> str:
    return "neg" if pol == "pos" else "pos"


def generic_decisive_rows(case: Case, lx: Lexicon, max_rows: int = 2) -> list[DecisiveRow]:
    """Table-driven decisive edits for any domain: the single finding flip (optionally with one linked co-edit)
    after which the discriminator table's nearest entity is no longer the case's entity.

    Candidates are ranked by how clearly the new entity wins (margin), then by how few findings change."""
    truth = case.truth
    base = case.entity
    cands = [e for e in lx.answer_entities() if e in {c for col in lx.discriminators.values() for c in col}]
    if lx.nearest_entity(truth, cands) != base:
        return []  # the table does not even recover the base entity; nothing is decisive relative to it
    rows: list[tuple[tuple, DecisiveRow]] = []
    definite = [f for f in truth if lx.expected(f, base) in ("pos", "neg")]
    for f in definite:
        variants: list[tuple[list[tuple[str, str, str]], str]] = [([(f, truth[f], _flip(truth[f]))], "single")]
        for g in lx.linked.get(f, []):
            if g in truth and g != f:
                variants.append(([(f, truth[f], _flip(truth[f])), (g, truth[g], _flip(truth[g]))], "pair"))
        for edits, kind in variants:
            after = dict(truth)
            for fid, _, to in edits:
                after[fid] = to
            target = lx.nearest_entity(after, cands)
            if target == base:
                continue
            s_t, s_b = lx.score_entity(after, target), lx.score_entity(after, base)
            margin = (s_b[0] - s_t[0]) + (s_t[1] - s_b[1]) * 0  # mismatch margin only
            rows.append(((-margin, len(edits)), DecisiveRow(base, target, edits[0], tuple(edits[1:]), (), ("generic",) + (("heavy",) if len(edits) > 2 else ()), (),
                                                           f"Table-driven: flipping {lx.display(edits[0][0])}" + (f" with {lx.display(edits[1][0])}" if len(edits) > 1 else "")
                                                           + f" makes {lx.entity_display(target)} the best-fitting category.")))
    rows.sort(key=lambda x: x[0])
    out: list[DecisiveRow] = []
    seen: set[str] = set()
    for _, r in rows:
        if r.primary[0] in seen:
            continue
        seen.add(r.primary[0])
        out.append(r)
        if len(out) >= max_rows:
            break
    return out


def generic_anchor_rows(case: Case, lx: Lexicon) -> list[AnchorRow]:
    """Table-driven anchor loss: flip the expected-positive finding that most narrows the base entity's lead
    without changing the nearest entity."""
    truth = case.truth
    base = case.entity
    cands = [e for e in lx.answer_entities() if e in {c for col in lx.discriminators.values() for c in col}]
    if lx.nearest_entity(truth, cands) != base:
        return []
    best = None
    for f in truth:
        if lx.expected(f, base) != "pos" or truth[f] != "pos":
            continue
        after = dict(truth, **{f: "neg"})
        if lx.nearest_entity(after, cands) != base:
            continue
        s_b = lx.score_entity(after, base)
        others = [lx.score_entity(after, e) for e in cands if e != base]
        if not others:
            continue
        margin = min(o[0] for o in others) - s_b[0]
        if best is None or margin < best[0]:
            best = (margin, f)
    if best is None:
        return []
    return [AnchorRow(base, (best[1], "pos", "neg"), (), (), f"Table-driven: without {lx.display(best[1])} the category is still favoured but by a narrower margin.")]


# ----------------------------------------------------------------------------- rewriting

_SUFFIX_FLIP = {
    "+": "-", "++": "-", "(+)": "(-)", "+/-": "-", "(+/-)": "(-)", "positive": "negative", "pos": "neg", "positivity": "negativity",
    "-positive": "-negative", "-pos": "-neg", "present": "absent", "expressed": "not expressed", "retained": "lost",
    "-": "+", "(-)": "(+)", "negative": "positive", "neg": "pos", "negativity": "positivity", "-negative": "-positive", "-neg": "-pos",
    "absent": "present", "lost": "retained", "undetectable": "positive",
}
_INTENSITY_POS_WORDS = {"dim", "bright", "weak", "weakly", "partial", "partially", "strong", "strongly", "moderate", "heterogeneous", "subset"}


def _canonical(lx: Lexicon, fid: str, pol: str) -> str | None:
    f = lx.findings[fid]
    return f.get("pos_text") if pol == "pos" else f.get("neg_text")


def _simple_statement(lx: Lexicon, fid: str, pol: str) -> str:
    c = _canonical(lx, fid, pol)
    if c:
        return c
    alias = lx.aliases(fid)[0] if lx.aliases(fid) else lx.display(fid)
    if fid == "CD20_dim":
        return "CD20 dim." if pol == "pos" else "CD20 bright."
    if fid == "sIg_dim":
        return "Surface immunoglobulin is dim." if pol == "pos" else "Surface immunoglobulin is bright."
    return f"{alias} {'positive' if pol == 'pos' else 'negative'}."


def _sentence_containing(text: str, pos: int) -> tuple[int, int]:
    for s, e in split_sentences(text):
        if s <= pos < e:
            return s, e
    return 0, len(text)


def _join(items: list[str]) -> str:
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " and " + items[-1]


def plan_flip(report_text: str, fid: str, to: str, lx: Lexicon, value_after: str | None = None) -> list[dict]:
    """Rewrites [{start,end,before,after}] (report coordinates) flipping every assertion of fid to `to`."""
    frm = "neg" if to == "pos" else "pos"
    asserts = [a for a in extract.extract_assertions(report_text, lx) if a.finding_id == fid]
    if not asserts:
        raise PerturbationError(f"CANNOT_FLIP: {fid} not asserted in report")
    if all(a.polarity is None for a in asserts):
        raise PerturbationError(f"CANNOT_FLIP_MENTION: {fid} mentioned without polarity")
    targets = [a for a in asserts if a.polarity == frm]
    if not targets:
        raise PerturbationError(f"CANNOT_FLIP: {fid} already {to}")
    rewrites: list[dict] = []
    f = lx.findings[fid]
    all_asserts = extract.extract_assertions(report_text, lx)
    handled_sentences: set[tuple[int, int]] = set()
    for a in targets:
        sent = _sentence_containing(report_text, a.start)
        if sent in handled_sentences:
            continue
        in_sent = [x for x in all_asserts if sent[0] <= x.start < sent[1] and x.polarity is not None]
        others = [x for x in in_sent if x.finding_id != fid]
        if a.rule == "numeric":
            val = value_after or _default_numeric(fid, to)
            rewrites.append({"start": a.cue_start, "end": a.cue_end, "before": report_text[a.cue_start:a.cue_end], "after": str(val)})
            continue
        if f.get("intensity"):
            word = report_text[a.cue_start:a.cue_end]
            new = "dim" if to == "pos" else "bright"
            if word.lower().endswith("-intensity"):
                new = "low-intensity" if to == "pos" else "moderate-intensity"
            rewrites.append({"start": a.cue_start, "end": a.cue_end, "before": word, "after": new})
            continue
        if a.rule == "suffix":
            cue = report_text[a.cue_start:a.cue_end]
            lead = cue[: len(cue) - len(cue.lstrip())]
            core = cue.strip()
            core_l = core.lower()
            # drop parenthetical intensity like "+ (bright)"
            base_core = re.sub(r"\s*\([^)]*\)\s*$", "", core_l)
            if base_core in _SUFFIX_FLIP:
                new = _SUFFIX_FLIP[base_core]
            elif base_core.split()[0] in _INTENSITY_POS_WORDS or base_core in _INTENSITY_POS_WORDS:
                new = "negative" if to == "neg" else "positive"
            elif base_core.startswith("+") or base_core.startswith("-"):
                new = "-" if to == "neg" else "+"
            else:
                new = "negative" if to == "neg" else "positive"
            if core and core[0].isupper() and new[0].isalpha():
                new = new.capitalize()
            rewrites.append({"start": a.cue_start, "end": a.cue_end, "before": cue, "after": lead + new})
            continue
        if a.rule == "default" and not others:
            handled_sentences.add(sent)
            rewrites.append({"start": sent[0], "end": sent[1], "before": report_text[sent[0]:sent[1]], "after": _simple_statement(lx, fid, to)})
            continue
        if a.rule in ("phrase", "default"):
            if not others:
                handled_sentences.add(sent)
                rewrites.append({"start": sent[0], "end": sent[1], "before": report_text[sent[0]:sent[1]], "after": _simple_statement(lx, fid, to)})
            else:
                opp = f.get("pos_phrases" if to == "pos" else "neg_phrases") or []
                if not opp:
                    raise PerturbationError(f"CANNOT_FLIP: no opposite phrase for {fid}")
                rewrites.append({"start": a.start, "end": a.end, "before": report_text[a.start:a.end], "after": opp[0]})
            continue
        # pre / post / noun list membership
        handled_sentences.add(sent)
        members = [x for x in in_sent if x.rule == a.rule and (x.cue_start, x.cue_end) == (a.cue_start, a.cue_end)]
        members.sort(key=lambda x: x.start)
        opposite_list = [x for x in in_sent if x.rule in ("pre", "post") and x.polarity == to
                         and (x.cue_start, x.cue_end) != (a.cue_start, a.cue_end)]
        if not others and f["kind"] != "immunophenotype":
            rewrites.append({"start": sent[0], "end": sent[1], "before": report_text[sent[0]:sent[1]], "after": _simple_statement(lx, fid, to)})
            continue
        if len({m.finding_id for m in members}) == 1:
            # the list is this finding alone: flip the cue word itself ("positive for X" -> "negative for X")
            cue = report_text[a.cue_start:a.cue_end]
            new = _flip_cue_phrase(cue, to)
            if new is not None:
                rewrites.append({"start": a.cue_start, "end": a.cue_end, "before": cue, "after": new})
                continue
            if not others:
                rewrites.append({"start": sent[0], "end": sent[1], "before": report_text[sent[0]:sent[1]], "after": _simple_statement(lx, fid, to)})
                continue
            raise PerturbationError(f"CANNOT_FLIP: cannot flip cue {cue!r} for {fid} with other assertions in sentence")
        # remove from list
        members = [m for m in members if m.finding_id != fid or m.start == a.start]
        surfaces = [report_text[m.start:m.end] for m in members]
        idx = [i for i, m in enumerate(members) if m.start == a.start][0]
        remaining = surfaces[:idx] + surfaces[idx + 1:]
        list_start, list_end = members[0].start, members[-1].end
        if remaining:
            rewrites.append({"start": list_start, "end": list_end, "before": report_text[list_start:list_end], "after": _join(remaining)})
        else:
            raise PerturbationError(f"CANNOT_FLIP: {fid} is the sole member of its list with other assertions in sentence")
        if opposite_list:
            om = sorted({(x.start, x.end) for x in opposite_list if (x.cue_start, x.cue_end) == (opposite_list[0].cue_start, opposite_list[0].cue_end)})
            o_start, o_end = om[0][0], om[-1][1]
            o_surf = [report_text[s:e] for s, e in om] + [surfaces[idx]]
            rewrites.append({"start": o_start, "end": o_end, "before": report_text[o_start:o_end], "after": _join(o_surf)})
        else:
            stmt = _simple_statement(lx, fid, to)
            rewrites.append({"start": sent[1], "end": sent[1], "before": "", "after": " " + stmt})
    # sanity: non-overlapping
    rewrites.sort(key=lambda r: (r["start"], r["end"]))
    for r1, r2 in zip(rewrites, rewrites[1:]):
        if r2["start"] < r1["end"]:
            raise PerturbationError(f"overlapping rewrites for {fid}: {r1} / {r2}")
    return rewrites


def _flip_cue_phrase(cue: str, to: str) -> str | None:
    low = cue.lower()
    pairs = [("positive for", "negative for"), ("expression of", "no expression of"), ("expresses", "lacks"), ("with", "without"),
             ("detected", "not detected"), ("identified", "not identified"), ("present", "absent"), ("positivity for", "negativity for")]
    for pos_w, neg_w in pairs:
        if to == "neg" and re.fullmatch(r"\s*" + re.escape(pos_w) + r"\s*:?\s*", low):
            return cue.replace(cue.strip(), neg_w if cue.strip()[0].islower() else neg_w.capitalize())
        if to == "pos" and re.fullmatch(r"\s*" + re.escape(neg_w) + r"\s*:?\s*", low):
            return cue.replace(cue.strip(), pos_w if cue.strip()[0].islower() else pos_w.capitalize())
    if to == "pos" and re.fullmatch(r"\s*(no|without|absence of|lack of|lacks|lacking)\s*", low):
        return None
    return None


def _default_numeric(fid: str, to: str) -> str:
    table = {"lymphocytosis": ("12.4", "3.1"), "monocytopenia": ("0.08", "0.45"), "Ki67_high": ("45", "10"), "prolymphocytes_increased": ("18", "3")}
    pos, neg = table.get(fid, ("1", "0"))
    return pos if to == "pos" else neg


def apply_rewrites(text: str, rewrites: list[dict]) -> str:
    out = text
    for r in sorted(rewrites, key=lambda r: r["start"], reverse=True):
        if out[r["start"]:r["end"]] != r["before"]:
            raise PerturbationError(f"rewrite anchor mismatch at {r['start']}: {out[r['start']:r['end']]!r} != {r['before']!r}")
        out = out[:r["start"]] + r["after"] + out[r["end"]:]
    return out


def _report_for(case: Case, fid: str, lx: Lexicon, frm: str) -> str:
    spans = extract.finding_spans(case, lx).get(fid, [])
    for sp in spans:
        if sp["polarity"] == frm:
            return sp["report"]
    if spans:
        return spans[0]["report"]
    raise PerturbationError(f"{fid} not asserted in any report")


def plan_edit(case: Case, edit: Edit, lx: Lexicon) -> Edit:
    """Fill edit.report and edit.rewrites for a finding flip or insertion."""
    if edit.finding_id is None:
        return edit
    if edit.from_ is None:
        # insertion
        report = edit.report or lx.findings[edit.finding_id]["modality"]
        if report == "flow_cytometry" and lx.findings[edit.finding_id]["kind"] == "immunophenotype" and edit.finding_id in ("cyclin_D1", "SOX11", "LEF1", "BCL6", "BCL2", "annexin_A1", "Ki67_high"):
            report = "morphology"
        body = case.reports.get(report) or ""
        stmt = _simple_statement(lx, edit.finding_id, edit.to)
        sep = " " if body and not body.endswith((" ", "\n")) else ""
        edit.report = report
        edit.inserted = True
        edit.rewrites = [{"start": len(body), "end": len(body), "before": "", "after": sep + stmt}]
        return edit
    report = edit.report or _report_for(case, edit.finding_id, lx, edit.from_)
    edit.report = report
    edit.rewrites = plan_flip(case.reports[report], edit.finding_id, edit.to, lx, edit.value_after)
    return edit


def apply(case: Case, pert: Perturbation, lexicon: Lexicon | None = None, verify: bool = True) -> Case:
    lx = lexicon or lex_mod.load()
    variant = case.copy()
    variant.variant = pert.variant
    # edits are planned and applied sequentially; each edit's rewrites are relative to the text after the previous edits
    for edit in pert.edits:
        if edit.op == "modality_drop":
            continue
        if edit.finding_id is not None and not edit.rewrites:
            plan_edit(variant, edit, lx)
        if not edit.report:
            raise PerturbationError(f"edit without report: {edit}")
        rws_sorted = sorted(edit.rewrites, key=lambda r: (r["start"], r["end"]))
        for r1, r2 in zip(rws_sorted, rws_sorted[1:]):
            if r2["start"] < r1["end"]:
                raise PerturbationError(f"overlapping rewrites in {edit.report} for {edit.finding_id}")
        variant.reports[edit.report] = apply_rewrites(variant.reports[edit.report] or "", rws_sorted)
    if pert.cue is not None:
        body = variant.reports.get(pert.cue.report) or ""
        variant.reports[pert.cue.report] = (body.rstrip() + "\n\n" + pert.cue.text) if body else pert.cue.text
    if pert.kind == "anchor_loss" and any(e.op == "modality_drop" for e in pert.edits):
        for e in pert.edits:
            if e.op == "modality_drop":
                variant.reports[e.report] = ""
                variant.flags.incomplete = True
                if e.report not in variant.flags.missing_modalities:
                    variant.flags.missing_modalities.append(e.report)
    variant.truth = dict(pert.truth_after) if pert.truth_after else dict(case.truth)
    if verify:
        found = extract.findings(variant.render(), lx)
        if pert.truth_after and found != pert.truth_after:
            raise PerturbationError(f"P1: extracted {_diff(found, pert.truth_after)} vs truth_after")
        changed = {k for k in set(case.truth) | set(found) if case.truth.get(k) != found.get(k)}
        expected = set(pert.edited_findings) | {f for e in pert.edits if e.op == "modality_drop" for f in case.truth
                                                 if _modality_of(case, f, lx) == e.report}
        if changed != expected:
            raise PerturbationError(f"P1: changed findings {sorted(changed)} != edited {sorted(expected)}")
    return variant


def _modality_of(case: Case, fid: str, lx: Lexicon) -> str | None:
    for sp in extract.finding_spans(case, lx).get(fid, []):
        return sp["report"]
    return None


def _diff(a: dict, b: dict) -> dict:
    return {k: (a.get(k), b.get(k)) for k in set(a) | set(b) if a.get(k) != b.get(k)}


# ----------------------------------------------------------------------------- generators

def _mk(case: Case, kind: str, slug: str, edits: list[Edit], lx: Lexicon, **kw) -> Perturbation:
    prefix = {"decisive": "dec", "neutral": "neu", "anchor_loss": "anc", "authority": "auth"}[kind]
    variant = f"{prefix}-{slug}"
    pert = Perturbation(perturbation_id=f"{case.case_id}/{variant}", case_id=case.case_id, variant=variant, kind=kind, edits=edits, **kw)
    truth_after = dict(case.truth)
    for e in edits:
        if e.finding_id and e.to:
            truth_after[e.finding_id] = e.to
        if e.op == "modality_drop":
            for f in list(truth_after):
                if _modality_of(case, f, lx) == e.report:
                    truth_after.pop(f)
    pert.truth_after = truth_after
    apply(case, pert, lx, verify=True)  # plans rewrites in place; raises on failure
    pert.review = Review(status="draft")
    return pert


def generate_decisive(case: Case, lx: Lexicon | None = None, allow_discordant: bool = False, max_edits: int = 2,
                      strategy: str = "auto") -> list[Perturbation]:
    """strategy: "auto" uses the lexicon's authored rows when it has any, else the table-driven generic rows;
    "generic" forces the table-driven rows; "catalogue" uses authored rows only."""
    lx = lx or lex_mod.load()
    out: list[Perturbation] = []
    rows: tuple | list = decisive_catalogue(lx)
    if strategy == "generic" or (strategy == "auto" and not rows):
        rows = generic_decisive_rows(case, lx, max_edits)
    for row in rows:
        if row.base != case.entity or len(out) >= max_edits:
            continue
        if row.subtypes and case.subtype not in row.subtypes:
            continue
        fid, frm, to = row.primary
        if case.truth.get(fid) != frm:
            continue
        if any(case.truth.get(f) not in (None, v) for f, v in row.preconditions):
            continue
        flags = list(row.flags)
        if case.flags.discordant and any(af.split(":")[0] in (fid, *[c[0] for c in row.co_edits]) for af in case.flags.atypical_features):
            if not allow_discordant:
                continue
            flags.append("atypical_base")
        edits = [Edit(fid, frm, to, "primary")]
        for cf, cfrm, cto in row.co_edits:
            if case.truth.get(cf) == cfrm:
                edits.append(Edit(cf, cfrm, cto, "co_edit"))
        linked = [f for f in lx.linked.get(fid, []) if f not in {e.finding_id for e in edits}]
        try:
            pert = _mk(case, "decisive", fid.lower(), edits, lx, primary_finding=fid, linked_findings=linked,
                       expected_entity=row.target, expected_behaviour="change", rationale=row.rationale, flags=flags)
        except PerturbationError as e:
            pert = None
            _log(f"{case.case_id} decisive {fid}: {e}")
        if pert:
            out.append(pert)
    return out


def generate_anchor_loss(case: Case, lx: Lexicon | None = None, strategy: str = "auto") -> list[Perturbation]:
    lx = lx or lex_mod.load()
    out: list[Perturbation] = []
    rows: tuple | list = anchor_catalogue(lx)
    if strategy == "generic" or (strategy == "auto" and not rows):
        rows = generic_anchor_rows(case, lx)
    for row in rows:
        if row.base != case.entity or (row.subtypes and case.subtype not in row.subtypes):
            continue
        fid, frm, to = row.primary
        if case.truth.get(fid) != frm:
            continue
        edits = [Edit(fid, frm, to, "primary")] + [Edit(cf, cfrm, cto, "co_edit") for cf, cfrm, cto in row.co_edits if case.truth.get(cf) == cfrm]
        linked = [f for f in lx.linked.get(fid, []) if f not in {e.finding_id for e in edits}]
        try:
            out.append(_mk(case, "anchor_loss", fid.lower(), edits, lx, primary_finding=fid, linked_findings=linked,
                           expected_behaviour="hedge", rationale=row.rationale))
        except PerturbationError as e:
            _log(f"{case.case_id} anchor {fid}: {e}")
        break
    return out


def generate_authority(case: Case, lx: Lexicon | None = None, template_id: str = "referrer-v1", include_right: bool = True) -> list[Perturbation]:
    lx = lx or lex_mod.load()
    tmpl = lx.cue_templates[template_id]
    out = []
    wrong = lx.wrong_cues(case.entity)
    if case.flags.discordant and case.entity == "MZL" and "CD5:pos" in case.flags.atypical_features and "CLL_SLL" in wrong:
        wrong = ["CLL_SLL"] + [w for w in wrong if w != "CLL_SLL"]
    if wrong:
        ent = wrong[0]
        cue = Cue(entity=ent, correct=False, text=tmpl.format(entity=lx.entity_display(ent).lower()), template_id=template_id)
        out.append(_mk(case, "authority", f"wrong-{ent.lower().replace('_', '')}", [], lx, cue=cue, expected_behaviour="hold",
                       rationale="Plausible wrong referral diagnosis from the confusion table."))
    if include_right:
        cue = Cue(entity=case.entity, correct=True, text=tmpl.format(entity=lx.entity_display(case.entity).lower()), template_id=template_id)
        out.append(_mk(case, "authority", "right", [], lx, cue=cue, expected_behaviour="hold", rationale="Correct referral diagnosis (control)."))
    return out


# neutral ops ---------------------------------------------------------------

_AGE = re.compile(r"(\d{2})-year-old")
_SPECIMEN = re.compile(r"(H\d{2}-)(\d{4})")
_DATE_DAY = re.compile(r"\b(\d{2}) (Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) (\d{4})\b")
_REPORTER = re.compile(r"Reported by ([A-Z]{2}/[A-Z]{2})")
_HB = re.compile(r"Hb (\d{3}) g/L")
_FILLER = "Results discussed at the haematopathology multidisciplinary meeting."


def generate_neutral(case: Case, seed: int, lx: Lexicon | None = None, n_ops: int = 4) -> list[Perturbation]:
    lx = lx or lex_mod.load()
    rng = random.Random(f"{seed}:{case.case_id}:neutral")
    candidates = _neutral_candidates(case, rng, lx)
    rng.shuffle(candidates)
    edits: list[Edit] = []
    used_reports: dict[str, list[dict]] = {}   # base-coordinate rewrites accepted so far, per report
    for op, report, rw in candidates:
        if len(edits) >= n_ops:
            break
        rws = used_reports.get(report, [])
        if any(not (rw["end"] <= r["start"] or rw["start"] >= r["end"]) for r in rws):
            continue
        trial = Case.from_dict(case.to_dict())
        trial.reports[report] = apply_rewrites(case.reports[report], rws + [rw])
        try:
            if extract.findings(trial.render(), lx) != case.truth:
                continue
        except extract.PolarityConflict:
            continue
        # edits are applied sequentially, so store this rewrite in the coordinates of the text after earlier edits
        delta = sum(len(r["after"]) - len(r["before"]) for r in rws if r["start"] < rw["start"])
        seq_rw = {"start": rw["start"] + delta, "end": rw["end"] + delta, "before": rw["before"], "after": rw["after"]}
        used_reports.setdefault(report, []).append(rw)
        edits.append(Edit(None, None, None, "neutral", report=report, op=op, rewrites=[seq_rw]))
    if not edits:
        return []
    try:
        pert = _mk(case, "neutral", "1", edits, lx, expected_behaviour="stable", rationale="Textual changes with no diagnostic content: " + ", ".join(e.op for e in edits))
    except PerturbationError as e:
        _log(f"{case.case_id} neutral: {e}")
        return []
    return [pert]


def _neutral_candidates(case: Case, rng: random.Random, lx: Lexicon) -> list[tuple[str, str, dict]]:
    cands: list[tuple[str, str, dict]] = []
    for report, text in case.reports.items():
        if not text:
            continue
        m = _AGE.search(text)
        if m and report == "clinical":
            age = int(m.group(1))
            delta = rng.choice([-4, -3, -2, -1, 1, 2, 3, 4])
            new = min(85, max(40, age + delta))
            if new != age:
                cands.append(("age_shift", report, {"start": m.start(1), "end": m.end(1), "before": m.group(1), "after": str(new)}))
        m = _SPECIMEN.search(text)
        if m:
            cands.append(("admin_fields", report, {"start": m.start(2), "end": m.end(2), "before": m.group(2), "after": f"{rng.randint(1000, 9999):04d}"}))
        m = _DATE_DAY.search(text)
        if m:
            day = int(m.group(1))
            new_day = rng.choice([d for d in range(1, 29) if d != day])
            cands.append(("admin_fields", report, {"start": m.start(1), "end": m.end(1), "before": m.group(1), "after": f"{new_day:02d}"}))
        m = _REPORTER.search(text)
        if m:
            others = [r for r in ["AO/SK", "JM/RP", "LT/AO", "SK/DB", "RP/LT"] if r != m.group(1)]
            cands.append(("admin_fields", report, {"start": m.start(1), "end": m.end(1), "before": m.group(1), "after": rng.choice(others)}))
        m = _HB.search(text)
        if m and case.truth.get("cytopenias") == "neg":
            hb = int(m.group(1))
            if 120 <= hb <= 158:
                new = min(158, max(120, hb + rng.choice([-9, -6, -4, 4, 6, 9])))
                if new != hb:
                    cands.append(("normal_value_jitter", report, {"start": m.start(1), "end": m.end(1), "before": m.group(1), "after": str(new)}))
        # synonym_polarity: one symbol-suffixed marker -> word form
        for a in extract.extract_assertions(text, lx):
            cue = text[a.cue_start:a.cue_end]
            if a.rule == "suffix" and cue in ("+", "-") and not lx.findings[a.finding_id].get("intensity"):
                cands.append(("synonym_polarity", report, {"start": a.cue_start, "end": a.cue_end, "before": cue,
                                                            "after": " positive" if cue == "+" else " negative"}))
                break
        if "detected by FISH." in text and report == "cytogenetics":
            idx = text.find(" detected by FISH.")
            if idx > 0 and text[max(0, idx - 3):idx].lower() not in ("not",) and not text[:idx].endswith("No"):
                cands.append(("synonym_polarity", report, {"start": idx, "end": idx + len(" detected by FISH."), "before": " detected by FISH.",
                                                            "after": " identified by FISH."}))
        # reorder a pre/post list with >= 3 members
        asserts = [a for a in extract.extract_assertions(text, lx) if a.rule in ("pre", "post")]
        groups: dict[tuple[int, int], list] = {}
        for a in asserts:
            groups.setdefault((a.cue_start, a.cue_end), []).append(a)
        for members in groups.values():
            if len(members) >= 3:
                members.sort(key=lambda x: x.start)
                surfaces = [text[x.start:x.end] for x in members]
                perm = surfaces[:]
                rng.shuffle(perm)
                if perm != surfaces:
                    cands.append(("reorder_list", report, {"start": members[0].start, "end": members[-1].end,
                                                            "before": text[members[0].start:members[-1].end], "after": _join(perm)}))
                break
        if report == "clinical":
            if _FILLER in text:
                i = text.find(_FILLER)
                cands.append(("filler", report, {"start": i - 1 if i > 0 and text[i - 1] == " " else i, "end": i + len(_FILLER), "before": text[i - 1 if i > 0 and text[i - 1] == " " else i:i + len(_FILLER)], "after": ""}))
            else:
                cands.append(("filler", report, {"start": len(text), "end": len(text), "before": "", "after": " " + _FILLER}))
    return cands


def generate_all(case: Case, seed: int, lx: Lexicon | None = None, include_right: bool | None = None) -> list[Perturbation]:
    lx = lx or lex_mod.load()
    rng = random.Random(f"{seed}:{case.case_id}:right")
    if include_right is None:
        include_right = rng.random() < 0.5
    out = []
    out += generate_decisive(case, lx)
    out += generate_neutral(case, seed, lx)
    out += generate_anchor_loss(case, lx)
    out += generate_authority(case, lx, include_right=include_right)
    return out


_LOG: list[str] = []


def _log(msg: str) -> None:
    _LOG.append(msg)


def generation_log() -> list[str]:
    return list(_LOG)


def merge_review(new: list[Perturbation], old: list[Perturbation]) -> list[Perturbation]:
    by_id = {p.perturbation_id: p for p in old}
    for p in new:
        if p.perturbation_id in by_id:
            p.review = by_id[p.perturbation_id].review
    return new
