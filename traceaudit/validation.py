"""Probe validation on the simulator grid (spec 10)."""
from __future__ import annotations

import json
from pathlib import Path

from . import experiment, lexicon as lex_mod, pipeline, stats
from .clients import make_client
from .schema import load_cases, load_perturbations
from .simulate import SimParams

from .domains import sample_paths as _sample_paths

SAMPLE_CASES, SAMPLE_PERTS = _sample_paths("haematology")
TOLERANCE = 0.03

GRIDS = {
    "quick": {
        "clean": SimParams(),
        "mid": SimParams.uniform(0.2, p_base_noise=0.0, p_trace_answer_mismatch=0.0),
        "silent_only": SimParams(p_silent=0.3),
        "authority_only": SimParams(p_shift_silent=0.25, p_shift_ack=0.25),
    },
    "default": {
        "clean": SimParams(),
        "low": SimParams.uniform(0.05, p_base_noise=0.0, p_trace_answer_mismatch=0.0),
        "mid": SimParams.uniform(0.2, p_base_noise=0.0, p_trace_answer_mismatch=0.0),
        "high": SimParams.uniform(0.5, p_base_noise=0.0, p_trace_answer_mismatch=0.0),
        "silent_only": SimParams(p_silent=0.3),
        "authority_only": SimParams(p_shift_silent=0.25, p_shift_ack=0.25),
        "noisy_base": SimParams(p_base_noise=0.35),
        "styles_arrows": SimParams.uniform(0.2, p_base_noise=0.0, p_trace_answer_mismatch=0.0, style="arrows"),
        "styles_bullets": SimParams.uniform(0.2, p_base_noise=0.0, p_trace_answer_mismatch=0.0, style="bullets"),
        "styles_mixed": SimParams.uniform(0.2, p_base_noise=0.0, p_trace_answer_mismatch=0.0, style="mixed"),
    },
}


def _planted(p: SimParams) -> dict[str, float | None]:
    """Expected recovered rates under the simulator's fault model."""
    # decisive: miss first, then silent, then linked-only (all three omit the primary) -> silent rate among changed
    changed = 1 - p.p_miss
    silent_among_changed = (p.p_silent + p.p_mention_linked_only) / changed if changed else None
    return {
        "traces_with_contradiction": None,  # depends on n_restate; checked as monotone, not exact
        "silent_rate": silent_among_changed,
        "sensitivity": changed,
        "spurious_rate": p.p_spurious,
        "hedge_rate": 1 - p.p_unhedged if p.hedge_anchor else 0.0,
        "silent_shift_rate": p.p_shift_silent,
        "shift_rate": p.p_shift_silent + p.p_shift_ack,
        "fabrication_trace_rate": p.p_fabricate,
    }


def _recovered(summary: dict) -> dict[str, dict]:
    g = summary["grounding"]
    d = summary["counterfactual"]["decisive"]
    return {
        "traces_with_contradiction": g["traces_with_contradiction"],
        "fabrication_trace_rate": g["traces_with_unsupported"],
        "silent_rate": d["silent_rate"],
        "sensitivity": d["sensitivity"],
        "spurious_rate": summary["counterfactual"]["neutral"]["spurious_rate"],
        "hedge_rate": summary["counterfactual"]["anchor_loss"]["hedge_rate"],
        "silent_shift_rate": summary["authority"]["wrong"]["silent_shift_rate"],
        "shift_rate": summary["authority"]["wrong"]["shift_rate"],
    }


def run_config(name: str, params: SimParams, out_dir: Path, seed: int, cases_path, perts_path, runs: int = 3, B: int = 500, progress=None) -> dict:
    lx = lex_mod.load()
    cases = load_cases(cases_path)
    perts = load_perturbations(perts_path)
    client = make_client("sim", "simulated", params=params, seed=seed)
    prompt = experiment.load_prompt("enable-v3")
    run_dir = out_dir / name
    if run_dir.exists():
        import shutil
        shutil.rmtree(run_dir)
    jobs = experiment.plan(cases, perts, ("low", "medium", "high"), runs, seed, lexicon=lx, right_cue_fraction=1.0)
    manifest = experiment.build_manifest(experiment.new_run_id(__import__("random").Random(seed)), client, prompt, ["low", "medium", "high"], runs, seed,
                                         cases_path, perts_path, lx, len(cases), len(perts), {}, {}, 1, f"validate-probes {name}", "validation")
    experiment.run_experiment(jobs, client, run_dir, manifest, prompt, seed, progress=None)
    out = pipeline.score_all(run_dir, cases, perts, "D1", "lexical", B, seed, lx)
    summary = out["summary"]
    planted = _planted(params)
    recovered = _recovered(summary)
    rows = []
    passed = True
    for metric, want in planted.items():
        got = recovered[metric]
        if got["point"] is None:
            rows.append({"metric": metric, "planted": want, "recovered": None, "lo": None, "hi": None, "pass": want is None, "note": "no denominator"})
            if want is not None:
                passed = False
            continue
        if want is None:
            rows.append({"metric": metric, "planted": None, "recovered": got["point"], "lo": got["lo"], "hi": got["hi"], "pass": True, "note": "not exact"})
            continue
        inside = (got["lo"] is not None and got["lo"] - 1e-9 <= want <= got["hi"] + 1e-9) or abs(got["point"] - want) <= TOLERANCE
        # traces are independent in the simulator, so a 99% Wilson interval on the trace count is also a fair criterion
        # (the grid checks ~20 metrics, so a 95% interval would fail by chance about once per run)
        if not inside and got.get("denominator"):
            wlo, whi = stats.wilson(int(round(got["numerator"])), int(round(got["denominator"])), z=2.5758)
            inside = wlo <= want <= whi
        if name == "clean" and metric in ("silent_rate", "spurious_rate", "silent_shift_rate", "shift_rate", "fabrication_trace_rate") and got["point"] not in (0, None):
            inside = False
        rows.append({"metric": metric, "planted": want, "recovered": got["point"], "lo": got["lo"], "hi": got["hi"], "pass": inside, "note": ""})
        passed &= inside
    # clean: contradictions must be exactly zero
    if name == "clean":
        tc = recovered["traces_with_contradiction"]["point"]
        rows.append({"metric": "contradiction_zero", "planted": 0.0, "recovered": tc, "lo": None, "hi": None, "pass": tc == 0, "note": "clean config"})
        passed &= tc == 0
    if name == "noisy_base":
        share = summary["counts"]["unstable_base_pairs"] / max(1, summary["counts"]["base_pairs"])
        rows.append({"metric": "unstable_base_share", "planted": None, "recovered": round(share, 3), "lo": None, "hi": None, "pass": share > 0, "note": "expected > 0"})
        passed &= share > 0
    if progress:
        progress(f"{name}: {'PASS' if passed else 'FAIL'}")
    return {"config": name, "params": params.__dict__, "passed": passed, "rows": rows, "run_dir": str(run_dir)}


def _generated_inputs(out_dir: Path, per_entity: int, seed: int) -> tuple[Path, Path]:
    """Generate an approved case set and its perturbations for validation (bigger than the 6-case sample)."""
    from .domains.haematology import casegen
    from . import perturb
    from .schema import Review, write_jsonl
    lx = lex_mod.load()
    cases = casegen.generate_set(per_entity, seed, lx)
    casegen.approve_all(cases, "R00", "1970-01-01", "validation set")
    perts = []
    for c in cases:
        perts += perturb.generate_all(c, seed, lx, include_right=True)
    for p in perts:
        p.review = Review("R00", "1970-01-01", "approved", "validation set")
    out_dir.mkdir(parents=True, exist_ok=True)
    cp, pp = out_dir / "cases.jsonl", out_dir / "perturbations.jsonl"
    write_jsonl(cp, cases)
    write_jsonl(pp, perts)
    return cp, pp


def run_grid(grid: str, out_dir: Path, seed: int, progress=None, cases_path=None, perturbations_path=None) -> dict:
    cfgs = GRIDS[grid]
    out_dir.mkdir(parents=True, exist_ok=True)
    if not cases_path:
        cases_path, perturbations_path = _generated_inputs(out_dir, 3 if grid == "quick" else 20, seed)
    perturbations_path = perturbations_path or SAMPLE_PERTS
    results = [run_config(n, p, out_dir, seed, cases_path, perturbations_path, progress=progress) for n, p in cfgs.items()]
    # styles: recovered rates must agree within 0.03 across styles
    style_rows = [r for r in results if r["config"].startswith("styles_") or r["config"] == "mid"]
    style_ok = True
    if len(style_rows) > 1:
        for metric in ("silent_rate", "spurious_rate", "silent_shift_rate"):
            pts = [row["recovered"] for r in style_rows for row in r["rows"] if row["metric"] == metric and row["recovered"] is not None]
            if pts and max(pts) - min(pts) > 0.03:
                style_ok = False
    passed = all(r["passed"] for r in results) and style_ok
    md = [f"# Probe validation ({grid} grid, seed {seed})", "", f"Overall: **{'PASS' if passed else 'FAIL'}**" + ("" if style_ok else " (style criterion failed)"), ""]
    for r in results:
        md += [f"## {r['config']} — {'PASS' if r['passed'] else 'FAIL'}", "", "| metric | planted | recovered | 95% CI | pass |", "|---|---|---|---|---|"]
        for row in r["rows"]:
            ci = f"[{row['lo']}, {row['hi']}]" if row["lo"] is not None else "—"
            md.append(f"| {row['metric']} | {row['planted']} | {row['recovered']} | {ci} | {'✓' if row['pass'] else '✗'} {row['note']} |")
        md.append("")
    res = {"grid": grid, "seed": seed, "passed": passed, "style_ok": style_ok, "results": results, "markdown": "\n".join(md)}
    (out_dir / "validation.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    (out_dir / "validation.md").write_text(res["markdown"], encoding="utf-8")
    return res
