"""Running and scoring probe studies on fact-ledger cases (spec 19).

plan/run      path A: render every variant, prompt any client with ledger-v1, store replies as ordinary traces
ablate        second pass: remove the discriminators each base trace stated and rerun at the same effort
import_       path B: artefacts an external engine produced for exported variants become traces (and engine ablations)
score_all     ledger_probes.score_run -> stats.summarise -> stats.export_long, same files as a text run
"""
from __future__ import annotations

import datetime as _dt
import json
import random
import re
from pathlib import Path
from typing import Callable, Iterable

from . import experiment, ledger_io, ledger_perturb as LP, ledger_probes as LPR, stats
from .clients.base import ModelClient
from .experiment import EFFORTS, Job, append_scoring, read_manifest, write_manifest
from .importers import parse_markdown
from .ledger import LedgerCase
from .lexicon import Lexicon
from .schema import Perturbation, Trace, load_perturbations, load_traces, read_jsonl, write_jsonl

RENDERER_VERSION = 1


def _glob_match(value: str, patterns: list[str] | None) -> bool:
    import fnmatch
    return True if not patterns else any(fnmatch.fnmatch(value, p) for p in patterns)


def plan(cases: list[LedgerCase], perts: list[Perturbation], efforts: Iterable[str] = EFFORTS, runs_per_variant: int = 3, master_seed: int = 0,
         case_filter: list[str] | None = None, variant_filter: list[str] | None = None, allow_unreviewed: bool = False,
         right_cue_fraction: float = 0.5, evidence: bool = True, base_lexicon: Lexicon | None = None, evidence_policy: str = "rewrite") -> list[Job]:
    """Jobs for cases x variants x efforts x runs; the rendered text is the fact table the model will see."""
    jobs: list[Job] = []
    rng_right = random.Random(f"{master_seed}:auth-right")
    for c in cases:
        if case_filter and c.case_id not in case_filter:
            continue
        variants: list[tuple[str, str, dict, dict]] = []
        if _glob_match("base", variant_filter):
            variants.append(("base", ledger_io.render_case(c, evidence), LP.found_map(c),
                             {"kind": "base", "base_entity": c.truth, "surface": "ledger", "fingerprint": ledger_io.fact_fingerprint(c)}))
        for p in perts:
            if p.case_id != c.case_id or not _glob_match(p.variant, variant_filter):
                continue
            if not allow_unreviewed and p.review.status != "approved":
                continue
            if p.variant == "auth-right" and rng_right.random() >= right_cue_fraction:
                continue
            v = LP.apply(c, p, evidence_policy, base_lexicon)
            meta = {"kind": p.kind, "base_entity": c.truth, "primary_finding": p.primary_finding, "co_edits": p.co_edits,
                    "linked_findings": list(p.linked_findings), "expected_entity": p.expected_entity, "surface": "ledger",
                    "fingerprint": ledger_io.fact_fingerprint(v), "cue_entity": p.cue.entity if p.cue else None, "cue_fact": p.extra.get("cue_fact"),
                    "removed_fields": [e.extra.get("field") for e in p.edits if e.op in ("remove", "untest", "mask")],
                    "decision_before": p.extra.get("decision_before"), "hedged_before": p.extra.get("hedged_before"),
                    "edited_fields": {e.finding_id: e.extra.get("field") for e in p.edits if e.finding_id and e.op in ("set_value", "untest", "mask")}}
            variants.append((p.variant, ledger_io.render_case(v, evidence), dict(p.truth_after), meta))
        jobs += experiment.expand_jobs(c.case_id, variants, efforts, runs_per_variant)
    random.Random(master_seed).shuffle(jobs)  # [PRE-REG] interleaving
    return jobs


def manifest_for(run_id: str, client: ModelClient, prompt: dict, efforts: list[str], runs: int, seed: int, cases_path, perts_path,
                 n_cases: int, n_perts: int, filters: dict, sampling: dict, workers: int, notes: str = "", evidence: bool = True,
                 base_lexicon: Lexicon | None = None) -> dict:
    m = experiment.build_manifest(run_id, client, prompt, efforts, runs, seed, cases_path, perts_path, base_lexicon, n_cases, n_perts,
                                  filters, sampling, workers, notes)
    m["surface"] = "ledger"
    m["render"] = {"evidence": evidence, "renderer_version": RENDERER_VERSION}
    m["phases"] = [{"name": "probes", "started": m["created"]}]
    m["inputs"]["ablations"] = None
    return m


def run(jobs: list[Job], client: ModelClient, run_dir: str | Path, manifest: dict, prompt: dict, master_seed: int, **kw) -> dict:
    """experiment.run_experiment with the trace key kept out of the prompt."""
    return experiment.run_experiment(jobs, client, run_dir, manifest, prompt, master_seed, embed_trace_key=False, **kw)


# ----------------------------------------------------------------------------- ablation second pass

def plan_ablations(run_dir: str | Path, cases: list[LedgerCase], perts: list[Perturbation], mode: str = "remove", base_lexicon: Lexicon | None = None,
                   fallback_key_findings: bool = False) -> tuple[list[Perturbation], dict]:
    """One ablation perturbation per OK base trace that stated discriminators (ids restricted to the case's own facts)."""
    run_dir = Path(run_dir)
    traces = load_traces(run_dir / "traces.jsonl")
    views = LPR.build_views(cases, [], base_lexicon)
    out: list[Perturbation] = []
    skipped = {"no_discriminators": 0, "no_rationale": 0, "not_ok": 0}
    existing = {p.perturbation_id for p in perts}
    for t in sorted(traces, key=lambda t: t.trace_key):
        if t.variant != "base":
            continue
        if not t.ok:
            skipped["not_ok"] += 1
            continue
        view = views.get((t.case_id, "base"))
        if view is None:
            continue
        lt, _ = LPR.parse_trace(t, view, base_lexicon)
        if lt.rationale is None:
            skipped["no_rationale"] += 1
            continue
        ids = [i for d in lt.rationale.discriminators for i in d.get("ids", [])]
        if not ids and fallback_key_findings:
            ids = [i for kf in lt.rationale.key_findings for i in kf.get("ids", [])]
        pa, _ = ledger_io.ledger_answer(lt, view.case, base_lexicon)
        p = LP.plan_ablation(view.case, ids, t.effort, t.run, pa.entity, pa.hedged, t.trace_key, mode)
        if p is None:
            skipped["no_discriminators"] += 1
            continue
        p.review.status = "approved"
        if p.perturbation_id not in existing:
            out.append(p)
            existing.add(p.perturbation_id)
    return out, skipped


def ablate(run_dir: str | Path, cases: list[LedgerCase], perts: list[Perturbation], client: ModelClient | None, prompt: dict, master_seed: int,
           runs: int = 1, mode: str = "remove", export_dir: str | Path | None = None, base_lexicon: Lexicon | None = None, evidence: bool | None = None,
           progress: Callable[[str], None] | None = None, **run_kw) -> dict:
    """Plan the ablations from the base traces, record them in ablations.jsonl, then rerun (or export for an external engine)."""
    run_dir = Path(run_dir)
    manifest = read_manifest(run_dir)
    evidence = manifest.get("render", {}).get("evidence", True) if evidence is None else evidence
    path = run_dir / "ablations.jsonl"
    old = load_perturbations(path) if path.exists() else []
    new, skipped = plan_ablations(run_dir, cases, perts + old, mode, base_lexicon)
    allp = old + [p for p in new if p.perturbation_id not in {q.perturbation_id for q in old}]
    write_jsonl(path, allp)
    manifest["inputs"]["ablations"] = {"path": str(path), "n": len(allp), "mode": mode}
    manifest.setdefault("phases", []).append({"name": "ablation", "started": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
                                              "planned": len(new), "skipped": skipped, "runs": runs, "mode": mode})
    write_manifest(run_dir, manifest)
    if export_dir is not None:
        index = LP.export_variants(cases, allp, export_dir, evidence=evidence, base_lexicon=base_lexicon)
        return {"planned": len(new), "skipped": skipped, "exported": len(index)}
    if client is None:
        raise ValueError("a client is required to rerun ablations (or pass export_dir)")
    jobs = []
    for p in allp:
        effort = p.variant.split("-")[-2] if p.variant.startswith("abl-") else "medium"
        jobs += plan(cases, [p], [effort], runs, master_seed, allow_unreviewed=True, evidence=evidence, base_lexicon=base_lexicon)
    counts = run(jobs, client, run_dir, manifest, prompt, master_seed, progress=progress, **run_kw)
    return {"planned": len(new), "skipped": skipped, **counts}


# ----------------------------------------------------------------------------- path B: import artefacts

_EFFORT_RE = re.compile(r"think A/C:\s*`(\w+)`")
_REPEAT_RE = re.compile(r"repeat\s+(\d+)", re.I)


def import_artefacts(paths: Iterable[str | Path], run_dir: str | Path, cases: list[LedgerCase], perts: list[Perturbation],
                     index_path: str | Path | None = None, effort: str | None = None, model: str = "external",
                     base_lexicon: Lexicon | None = None) -> dict:
    """Artefacts produced for exported variants become traces. The variant is found from index.jsonl (fingerprint ->
    variant) or by matching the artefact's fact table against the applied variants; mismatches are excluded."""
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    views = LPR.build_views(cases, perts, base_lexicon)
    by_fp: dict[str, tuple[str, str]] = {ledger_io.fact_fingerprint(v.case): key for key, v in views.items()}
    if index_path:
        for rec in read_jsonl(index_path):
            by_fp.setdefault(rec["fingerprint"], (rec["case_id"], rec["variant"]))
    existing = experiment.existing_keys(run_dir)
    traces: list[Trace] = []
    engine_perts: list[Perturbation] = []
    problems: list[dict] = []
    for pth in paths:
        pth = Path(pth)
        text = pth.read_text(encoding="utf-8")
        case_v, lt = parse_markdown(text)
        head = text[: text.find("\n## ")] if "\n## " in text else text[:2000]
        eff = effort or (_EFFORT_RE.search(head).group(1) if _EFFORT_RE.search(head) else "medium")
        rep = _REPEAT_RE.search(head)
        run_idx = int(rep.group(1)) - 1 if rep else 0
        key = by_fp.get(ledger_io.fact_fingerprint(case_v))
        if key is None:
            problems.append({"path": str(pth), "code": "P1_LEDGER_IMPORT_MISMATCH", "case_id": case_v.case_id})
            continue
        case_id, variant = key
        tk = f"{case_id}|{variant}|{eff}|{run_idx}"
        if tk in existing or any(t.trace_key == tk for t in traces):
            problems.append({"path": str(pth), "code": "DUPLICATE_TRACE_KEY", "trace_key": tk})
            continue
        traces.append(Trace(tk, case_id, variant, eff, run_idx, model, lt.thinking, json.dumps(ledger_io.trace_to_dict(lt), ensure_ascii=False),
                            server="external", prompt_id="external", extra={"format": "ledger-json", "source": "enable-md", "artefact": str(pth)}))
        if lt.ablation is not None and variant == "base":
            view = views[(case_id, "base")]
            pa, _ = ledger_io.ledger_answer(lt, view.case, base_lexicon)
            p = LP.plan_ablation(view.case, lt.ablation.removed_ids, eff, run_idx, lt.ablation.decision_before or pa.entity, pa.hedged, tk, "remove", engine=True)
            if p is not None:
                p.review.status = "approved"
                if p.perturbation_id not in {q.perturbation_id for q in perts + engine_perts}:
                    engine_perts.append(p)
                after = ledger_io.LedgerTrace("", ledger_io.Report(lt.ablation.decision_after, [], lt.ablation.decision_after, None, None, []), None, None,
                                              {"engine_ablation": True})
                atk = f"{case_id}|{p.variant}|{eff}|0"
                if atk not in existing:
                    traces.append(Trace(atk, case_id, p.variant, eff, 0, model, "", json.dumps(ledger_io.trace_to_dict(after)), server="external",
                                        prompt_id="external", extra={"format": "ledger-json", "source": "engine-ablation", "artefact": str(pth)}))
    write_jsonl(run_dir / "traces.jsonl", traces, append=True)
    if engine_perts:
        path = run_dir / "ablations.jsonl"
        old = load_perturbations(path) if path.exists() else []
        write_jsonl(path, old + engine_perts)
    if not (run_dir / "manifest.json").exists():
        m = {"schema_version": 1, "run_id": run_dir.name, "created": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"), "status": "complete",
             "surface": "ledger", "model": {"tag": model, "server": "external", "client": "import"}, "prompt": {"id": "external", "sha256": None},
             "inputs": {"cases": None, "perturbations": None, "ablations": {"path": str(run_dir / "ablations.jsonl")} if engine_perts else None},
             "filters": {}, "notes": "imported artefacts", "scoring": [], "phases": [{"name": "import"}]}
        write_manifest(run_dir, m)
    else:
        m = read_manifest(run_dir)
        m.setdefault("phases", []).append({"name": "import", "n_traces": len(traces), "n_problems": len(problems)})
        if engine_perts:
            m["inputs"]["ablations"] = {"path": str(run_dir / "ablations.jsonl")}
        write_manifest(run_dir, m)
    return {"imported": len(traces), "engine_ablations": len(engine_perts), "problems": problems}


def cases_from_artefacts(paths: Iterable[str | Path]) -> tuple[list[LedgerCase], list[dict]]:
    """Base cases from artefacts (one per case id); repeats must carry the same fact table."""
    out: dict[str, LedgerCase] = {}
    fps: dict[str, str] = {}
    problems: list[dict] = []
    for pth in paths:
        case, _ = parse_markdown(Path(pth).read_text(encoding="utf-8"))
        fp = ledger_io.fact_fingerprint(case)
        if case.case_id in out:
            if fps[case.case_id] != fp:
                problems.append({"path": str(pth), "code": "FACTS_DIFFER_ACROSS_REPEATS", "case_id": case.case_id})
            continue
        out[case.case_id] = case
        fps[case.case_id] = fp
    return list(out.values()), problems


# ----------------------------------------------------------------------------- scoring

def resolve_inputs(run_dir: str | Path, cases_path: str | None = None, perts_path: str | None = None) -> tuple[list[LedgerCase], list[Perturbation]]:
    m = read_manifest(run_dir)
    cp = cases_path or (m.get("inputs", {}).get("cases") or {}).get("path")
    pp = perts_path or (m.get("inputs", {}).get("perturbations") or {}).get("path")
    if not cp or not Path(cp).exists():
        raise FileNotFoundError(f"ledger cases file not found: {cp!r}; pass --cases")
    cases = ledger_io.load_cases(cp)
    perts = load_perturbations(pp) if pp and Path(pp).exists() else []
    ap = (m.get("inputs", {}).get("ablations") or {}).get("path") or str(Path(run_dir) / "ablations.jsonl")
    if Path(ap).exists():
        have = {p.perturbation_id for p in perts}
        perts += [p for p in load_perturbations(ap) if p.perturbation_id not in have]
    return cases, perts


def score_all(run_dir: str | Path, cases: list[LedgerCase], perts: list[Perturbation], rule: str = "D1", B: int = 2000, seed: int = 20261020,
              base_lexicon: Lexicon | None = None, surfaces: tuple[str, ...] = LPR.SURFACES, evidence_policy: str = "rewrite", progress=None) -> dict:
    run_dir = Path(run_dir)
    out: dict = {"probes": LPR.score_run(run_dir, cases, perts, base_lexicon, surfaces, evidence_policy, progress)}
    LPR.claims_placeholder(run_dir)
    append_scoring(run_dir, "ledger_probes", {"rule": rule, "surfaces": list(surfaces), **out["probes"]})
    case_entities = {c.case_id: (c.truth or "UNKNOWN") for c in cases}
    out["summary"] = stats.summarise(run_dir, rule, B, seed, case_entities, None)
    out["summary"]["surface"] = "ledger"
    (run_dir / "summary.json").write_text(json.dumps(out["summary"], indent=1, ensure_ascii=False), encoding="utf-8")
    append_scoring(run_dir, "summary", {"rule": rule, "B": B, "seed": seed})
    stats.export_long(run_dir, run_dir / "long.csv", case_entities, {})
    return out
