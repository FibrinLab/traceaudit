"""Scoring pipeline over a run directory: segment + ground, probes, summary (spec 08 §3)."""
from __future__ import annotations

from pathlib import Path

from . import extract, grounding, perturb, probes, segment, stats
from . import lexicon as lex_mod
from .experiment import append_scoring, read_manifest
from .lexicon import Lexicon
from .schema import Case, Perturbation, load_cases, load_perturbations, load_traces, write_jsonl


def resolve_inputs(run_dir: str | Path, cases_path: str | None = None, perturbations_path: str | None = None) -> tuple[list[Case], list[Perturbation]]:
    m = read_manifest(run_dir)
    cp = cases_path or (m.get("inputs", {}).get("cases") or {}).get("path")
    pp = perturbations_path or (m.get("inputs", {}).get("perturbations") or {}).get("path")
    if not cp or not Path(cp).exists():
        raise FileNotFoundError(f"cases file not found: {cp!r}; pass --cases")
    cases = load_cases(cp)
    perts = load_perturbations(pp) if pp and Path(pp).exists() else []
    return cases, perts


def ground_run(run_dir: str | Path, cases: list[Case], perturbations: list[Perturbation], verifier: str | None = "lexical",
               lexicon: Lexicon | None = None, verifier_obj=None, progress=None) -> dict:
    lx = lexicon or lex_mod.load()
    run_dir = Path(run_dir)
    traces = load_traces(run_dir / "traces.jsonl")
    case_by = {c.case_id: c for c in cases}
    pert_by = {(p.case_id, p.variant): p for p in perturbations}
    ver = verifier_obj
    if ver is None:
        ver = {"lexical": grounding.LexicalVerifier(), "retrieval": grounding.RetrievalVerifier(), None: None, "none": None}.get(verifier)
    spans_cache: dict[tuple[str, str], tuple[dict, dict, str]] = {}
    claims_out = []
    g_out = []
    for i, t in enumerate(sorted(traces, key=lambda t: t.trace_key)):
        key = (t.case_id, t.variant)
        if key not in spans_cache:
            c = case_by.get(t.case_id)
            if c is None:
                continue
            if t.variant == "base":
                v = c
                entity_after = c.entity
            else:
                p = pert_by.get(key)
                if p is None:
                    continue
                v = perturb.apply(c, p, lx, verify=False)
                entity_after = p.expected_entity if p.kind == "decisive" else (None if p.kind == "anchor_loss" else c.entity)
            spans_cache[key] = (dict(v.truth), extract.finding_spans(v, lx), entity_after)
        truth, spans, entity_after = spans_cache[key]
        claims = segment.segment(t.reasoning, t.trace_key, lx) if t.ok else []
        rec = grounding.ground(t, truth, claims, spans, entity_after, ver, lx)
        claims_out.extend(claims)
        g_out.append(rec)
        if progress and (i + 1) % 200 == 0:
            progress(f"grounded {i + 1}/{len(traces)}")
    write_jsonl(run_dir / "claims.jsonl", claims_out)
    write_jsonl(run_dir / "grounding.jsonl", g_out)
    append_scoring(run_dir, "ground", {"verifier": verifier if ver else None, "lexicon_version": lx.version, "n_traces": len(g_out), "n_claims": len(claims_out)})
    return {"traces": len(g_out), "claims": len(claims_out)}


def score_all(run_dir: str | Path, cases: list[Case], perturbations: list[Perturbation], rule: str = "D1", verifier: str | None = "lexical",
              B: int = 2000, seed: int = 20261020, lexicon: Lexicon | None = None, progress=None, skip_ground: bool = False) -> dict:
    lx = lexicon or lex_mod.load()
    run_dir = Path(run_dir)
    out: dict = {}
    if not skip_ground or not (run_dir / "grounding.jsonl").exists():
        out["ground"] = ground_run(run_dir, cases, perturbations, verifier, lx, progress=progress)
    out["probes"] = probes.score_run(run_dir, perturbations, lx)
    append_scoring(run_dir, "probes", {"rule": rule, **out["probes"]})
    case_entities = {c.case_id: c.entity for c in cases}
    out["summary"] = stats.summarise(run_dir, rule, B, seed, case_entities, verifier)
    append_scoring(run_dir, "summary", {"rule": rule, "B": B, "seed": seed})
    stats.export_long(run_dir, run_dir / "long.csv", case_entities, {c.case_id: c.flags.to_dict() for c in cases})
    return out
