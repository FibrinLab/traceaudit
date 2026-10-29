import json
from pathlib import Path

import pytest

from traceaudit import experiment, importers, ledger_io, ledger_perturb as LP, ledger_pipeline as PL, ledger_synth
from traceaudit.ledger_sim import LedgerSimParams, LedgerSimulatedModel
from traceaudit.schema import load_traces, read_jsonl, write_jsonl

FIX = Path(__file__).with_name("fixtures") / "synthetic_trace_SYN-003.md"


def _inputs(tmp_path, per_candidate=1, seed=0):
    cases = ledger_synth.generate_set(per_candidate, seed)
    perts = []
    for c in cases:
        ps = LP.generate_all(c, seed, include_right=True)
        for p in ps:
            p.review.status = "approved"
        perts += ps
    cp, pp = tmp_path / "ledger_cases.jsonl", tmp_path / "ledger_perturbations.jsonl"
    ledger_io.write_cases(cp, cases)
    write_jsonl(pp, perts)
    return cases, perts, cp, pp


def _run(tmp_path, cases, perts, cp, pp, params=None, runs=3, efforts=("low", "medium"), seed=0):
    client = LedgerSimulatedModel.client(params or LedgerSimParams(), seed=seed)
    prompt = experiment.load_prompt("ledger-v1")
    jobs = PL.plan(cases, perts, efforts, runs, seed, right_cue_fraction=1.0)
    man = PL.manifest_for("r1", client, prompt, list(efforts), runs, seed, cp, pp, len(cases), len(perts), {}, {}, 1)
    run_dir = tmp_path / "run"
    counts = PL.run(jobs, client, run_dir, man, prompt, seed, sleep=lambda s: None)
    return client, prompt, run_dir, counts


def test_plan_renders_variants_without_leaks(tmp_path):
    cases, perts, cp, pp = _inputs(tmp_path)
    jobs = PL.plan(cases, perts, ("low",), 1, 0, right_cue_fraction=1.0)
    assert {j.variant for j in jobs} == {"base"} | {p.variant for p in perts}
    for j in jobs:
        assert "truth" not in j.rendered.lower() and j.case_id not in j.rendered and j.variant not in j.rendered
        assert j.meta["surface"] == "ledger" and j.meta["fingerprint"]
    dec = next(j for j in jobs if j.variant.startswith("dec-"))
    assert dec.meta["expected_entity"] and dec.meta["primary_finding"] and dec.truth_after
    unreviewed = PL.plan(cases, perts, ("low",), 1, 0, allow_unreviewed=False)
    assert {j.variant for j in unreviewed} == {"base"} | {p.variant for p in perts}  # all approved above
    for p in perts:
        p.review.status = "draft"
    assert {j.variant for j in PL.plan(cases, perts, ("low",), 1, 0)} == {"base"}


def test_run_score_end_to_end_clean(tmp_path):
    cases, perts, cp, pp = _inputs(tmp_path)
    client, prompt, run_dir, counts = _run(tmp_path, cases, perts, cp, pp)
    assert counts["errors"] == 0 and counts["ok"] == len(PL.plan(cases, perts, ("low", "medium"), 3, 0, right_cue_fraction=1.0))
    man = experiment.read_manifest(run_dir)
    assert man["surface"] == "ledger" and man["prompt"]["embed_trace_key"] is False and man["inputs"]["lexicon"] is None
    out = PL.score_all(run_dir, cases, perts, B=50)
    s = out["summary"]
    assert s["counterfactual"]["decisive"]["silent_rate"]["point"] == 0.0 and s["counterfactual"]["decisive"]["sensitivity"]["point"] == 1.0
    assert s["counterfactual"]["neutral"]["spurious_rate"]["point"] == 0.0 and s["counterfactual"]["anchor_loss"]["hedge_rate"]["point"] == 1.0
    assert s["authority"]["wrong"]["shift_rate"]["point"] == 0.0 and s["grounding"]["traces_with_contradiction"]["point"] == 0.0
    assert out["probes"]["contract_fallback"] == 0
    for name in ("grounding.jsonl", "counterfactual.jsonl", "authority.jsonl", "ledger_audit.jsonl", "summary.json", "long.csv", "claims.jsonl"):
        assert (run_dir / name).exists(), name
    assert json.loads((run_dir / "summary.json").read_text())["surface"] == "ledger"


def test_ablate_second_pass_is_resumable_and_scored(tmp_path):
    cases, perts, cp, pp = _inputs(tmp_path)
    client, prompt, run_dir, _ = _run(tmp_path, cases, perts, cp, pp, runs=2, efforts=("medium",))
    res = PL.ablate(run_dir, cases, perts, client, prompt, 0, runs=1, sleep=lambda s: None)
    n_base = sum(1 for t in load_traces(run_dir / "traces.jsonl") if t.variant == "base")
    assert res["planned"] == n_base and res["ok"] == n_base and res["skipped"]["no_discriminators"] == 0
    again = PL.ablate(run_dir, cases, perts, client, prompt, 0, runs=1, sleep=lambda s: None)
    assert again["planned"] == 0 and again["ok"] == 0
    man = experiment.read_manifest(run_dir)
    assert [ph["name"] for ph in man["phases"]] == ["probes", "ablation", "ablation"] and man["inputs"]["ablations"]["n"] == n_base
    cases2, perts2 = PL.resolve_inputs(run_dir)
    assert len(perts2) == len(perts) + n_base
    out = PL.score_all(run_dir, cases2, perts2, B=50)
    assert out["summary"]["counterfactual"]["ablation"]["load_bearing_rate"]["point"] == 1.0
    # export instead of rerun
    exp = PL.ablate(run_dir, cases, perts, None, prompt, 0, export_dir=tmp_path / "exp")
    assert exp["exported"] == len(cases) + n_base and (tmp_path / "exp" / "index.jsonl").exists()  # base cases + the ablation variants


def test_ablation_ignored_is_recovered(tmp_path):
    cases, perts, cp, pp = _inputs(tmp_path, per_candidate=2)
    client, prompt, run_dir, _ = _run(tmp_path, cases, perts, cp, pp, params=LedgerSimParams(p_ablation_ignored=1.0), runs=2, efforts=("medium",))
    PL.ablate(run_dir, cases, perts, client, prompt, 0, runs=1, sleep=lambda s: None)
    cases2, perts2 = PL.resolve_inputs(run_dir)
    out = PL.score_all(run_dir, cases2, perts2, B=50)
    assert out["summary"]["counterfactual"]["ablation"]["load_bearing_rate"]["point"] == 0.0


def test_import_artefact_and_mismatch(tmp_path):
    case, trace = importers.load(FIX)
    cases = [case]
    ex = LP.expectations(case, sources=("reference", "rationale"), rationales=[trace.rationale])
    perts = LP.generate_decisive(case, LP.expectation_lexicon(case, ex), ex)
    run_dir = tmp_path / "imp"
    res = PL.import_artefacts([FIX], run_dir, cases, perts)
    assert res["imported"] == 2 and res["engine_ablations"] == 1 and res["problems"] == []
    traces = load_traces(run_dir / "traces.jsonl")
    keys = {t.trace_key for t in traces}
    assert keys == {"SYN-003|base|medium|0", "SYN-003|abl-eng-medium-r0|medium|0"}
    base = next(t for t in traces if t.variant == "base")
    assert base.extra["format"] == "ledger-json" and base.extra["source"] == "enable-md" and base.reasoning
    cases2, perts2 = PL.resolve_inputs(run_dir, str(tmp_path / "cases.jsonl")) if False else (cases, perts + list(__import__("traceaudit.schema", fromlist=["load_perturbations"]).load_perturbations(run_dir / "ablations.jsonl")))
    out = PL.score_all(run_dir, cases2, perts2, B=20)
    cf = list(read_jsonl(run_dir / "counterfactual.jsonl"))
    assert len(cf) == 1 and cf[0]["kind"] == "ablation" and cf[0]["outcome"] == "not_load_bearing"
    g = {r["trace_key"]: r for r in read_jsonl(run_dir / "grounding.jsonl")}
    assert g["SYN-003|base|medium|0"]["n_contradicted"] == 0 and g["SYN-003|base|medium|0"]["contract_valid"] is False
    assert out["summary"]["counts"]["traces"] == 2
    # an artefact whose facts match no planned variant is excluded
    other = FIX.read_text(encoding="utf-8").replace("| p_1 | mk1 | Positive |", "| p_1 | mk1 | Weak |")
    (tmp_path / "x.md").write_text(other, encoding="utf-8")
    res2 = PL.import_artefacts([tmp_path / "x.md"], run_dir, cases, perts)
    assert res2["imported"] == 0 and res2["problems"][0]["code"] == "P1_LEDGER_IMPORT_MISMATCH"
    # importing the same artefact twice is a duplicate, not a second trace
    res3 = PL.import_artefacts([FIX], run_dir, cases, perts)
    assert res3["imported"] == 0 and res3["problems"][0]["code"] == "DUPLICATE_TRACE_KEY"


def test_import_matches_exported_variant_by_fingerprint(tmp_path):
    cases, perts, cp, pp = _inputs(tmp_path)
    dec = next(p for p in perts if p.kind == "decisive")
    index = LP.export_variants(cases, [dec], tmp_path / "exp")
    rec = next(r for r in index if r["variant"] == dec.variant)
    md = Path(rec["md"]).read_text()
    artefact = f"# Reasoning trace — {dec.case_id} — repeat 2\n\n- Model: `ext` · think A/C: `high`\n\n" + md + \
        '\n## 2. Model\'s own reasoning\n\n```\nf1 positive (p_1). Therefore K2.\n```\n\n## 3. Delivered report\n\n```json\n' + \
        json.dumps({"predicted_diagnosis": dec.expected_entity, "sections": [{"title": "Summary", "segments": [{"text": "f1 positive.", "citation_ids": ["p_1"]}]}]}) + "\n```\n"
    (tmp_path / "a.md").write_text(artefact, encoding="utf-8")
    res = PL.import_artefacts([tmp_path / "a.md"], tmp_path / "imp", cases, [dec], index_path=tmp_path / "exp" / "index.jsonl")
    assert res["imported"] == 1 and res["problems"] == []
    [t] = load_traces(tmp_path / "imp" / "traces.jsonl")
    assert t.trace_key == f"{dec.case_id}|{dec.variant}|high|1"


def test_cases_from_artefacts_dedupes_and_flags_drift(tmp_path):
    a = FIX.read_text(encoding="utf-8")
    (tmp_path / "r1.md").write_text(a, encoding="utf-8")
    (tmp_path / "r2.md").write_text(a.replace("repeat 1", "repeat 2"), encoding="utf-8")
    (tmp_path / "r3.md").write_text(a.replace("| p_1 | mk1 | Positive |", "| p_1 | mk1 | Weak |"), encoding="utf-8")
    cases, problems = PL.cases_from_artefacts([tmp_path / "r1.md", tmp_path / "r2.md", tmp_path / "r3.md"])
    assert [c.case_id for c in cases] == ["SYN-003"] and problems[0]["code"] == "FACTS_DIFFER_ACROSS_REPEATS"


@pytest.mark.parametrize("workers", [1, 3])
def test_workers_do_not_change_results(tmp_path, workers):
    cases, perts, cp, pp = _inputs(tmp_path)
    client = LedgerSimulatedModel.client(LedgerSimParams.uniform(0.3, p_base_noise=0.0), seed=0)
    prompt = experiment.load_prompt("ledger-v1")
    jobs = PL.plan(cases, perts, ("low",), 1, 0, right_cue_fraction=1.0)
    man = PL.manifest_for("r1", client, prompt, ["low"], 1, 0, cp, pp, len(cases), len(perts), {}, {}, workers)
    PL.run(jobs, client, tmp_path / f"w{workers}", man, prompt, 0, workers=workers, sleep=lambda s: None)
    got = {t.trace_key: (t.reasoning, t.answer) for t in load_traces(tmp_path / f"w{workers}" / "traces.jsonl")}
    ref_dir = tmp_path / "ref"
    PL.run(jobs, LedgerSimulatedModel.client(LedgerSimParams.uniform(0.3, p_base_noise=0.0), seed=0), ref_dir, dict(man), prompt, 0, sleep=lambda s: None)
    ref = {t.trace_key: (t.reasoning, t.answer) for t in load_traces(ref_dir / "traces.jsonl")}
    assert got == ref


def test_cli_ledger_subcommands(tmp_path, capsys):
    from traceaudit.cli import main
    d = tmp_path
    assert main(["ledger", "cases", str(FIX), "-o", str(d / "cases.jsonl")]) == 0
    assert main(["ledger", "perturb", str(d / "cases.jsonl"), "-o", str(d / "perts.jsonl"), "--rationale-from", str(FIX.parent), "--approve-all",
                 "--include-right", "--seed", "1"]) == 0
    perts = list(read_jsonl(d / "perts.jsonl"))
    kinds = {p["kind"] for p in perts}
    assert kinds == {"decisive", "neutral", "anchor_loss", "authority"} and all(p["review"]["status"] == "approved" for p in perts)
    assert any("model_derived" in p["flags"] for p in perts if p["kind"] == "decisive")
    assert main(["ledger", "validate", str(d / "cases.jsonl"), "--perturbations", str(d / "perts.jsonl")]) == 0
    assert main(["ledger", "export", str(d / "cases.jsonl"), "--perturbations", str(d / "perts.jsonl"), "-o", str(d / "exp")]) == 0
    assert (d / "exp" / "index.jsonl").exists() and (d / "exp" / "SYN-003" / "base.md").exists()
    rc = main(["ledger", "run", "--client", "sim", "--cases", str(d / "cases.jsonl"), "--perturbations", str(d / "perts.jsonl"), "--out", str(d / "run"),
               "--efforts", "medium", "--runs", "3", "--right-cue-fraction", "1", "--quiet", "--with-ablation", "--seed", "3"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert out["errors"] == 0 and out["ablation"]["planned"] == 3
    assert main(["ledger", "score", str(d / "run"), "--B", "50"]) == 0
    summary = json.loads((d / "run" / "summary.json").read_text())
    assert summary["surface"] == "ledger" and summary["counterfactual"]["decisive"]["sensitivity"]["point"] == 1.0
    assert summary["counterfactual"]["ablation"]["load_bearing_rate"]["point"] == 1.0
    assert main(["ledger", "ablate", str(d / "run"), "--export", str(d / "abl-exp")]) == 0
    assert (d / "abl-exp" / "index.jsonl").exists()
    assert main(["ledger", "import", str(FIX), "--run-dir", str(d / "imp"), "--cases", str(d / "cases.jsonl"), "--perturbations", str(d / "perts.jsonl")]) == 0
    assert main(["ledger", "score", str(d / "imp"), "--cases", str(d / "cases.jsonl"), "--perturbations", str(d / "perts.jsonl"), "--B", "20"]) == 0
    assert main(["ledger", "audit", str(FIX)]) == 1  # unchanged: the sample fails 9 checks
