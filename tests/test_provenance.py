"""Provenance hashes: recorded per trace and per run, recomputed by verify_run and `manifest verify`."""
from __future__ import annotations

import json
from pathlib import Path

from traceaudit import experiment, provenance
from traceaudit.clients.callable_ import CallableClient
from traceaudit.simulate import SimParams, SimulatedModel
from traceaudit.textutil import sha256_text

PKG = Path(__file__).resolve().parents[1] / "traceaudit"
CASES = PKG / "domains" / "haematology" / "sample_cases.jsonl"
PERTS = PKG / "domains" / "haematology" / "sample_perturbations.jsonl"


def _run(tmp_path, cases, perts, lx, cases_path=CASES, perts_path=PERTS):
    sim = SimulatedModel(SimParams(), lx, seed=1)
    client = CallableClient(sim)
    prompt = experiment.load_prompt("enable-v3")
    jobs = experiment.plan(cases, perts, ["low"], 1, 0, allow_unreviewed=True, lexicon=lx, right_cue_fraction=1.0)
    man = experiment.build_manifest("x", client, prompt, ["low"], 1, 0, cases_path, perts_path, lx, len(cases), len(perts), {}, {}, 1)
    experiment.run_experiment(jobs, client, tmp_path, man, prompt, 0, progress=None)
    return jobs, prompt


def test_hash_rules_are_plain_sha256():
    h = provenance.trace_hashes("sys", "usr", "think", "ans")
    assert h["prompt_sha256"] == sha256_text("sys\x00usr")
    assert h["reasoning_sha256"] == sha256_text("think") and h["answer_sha256"] == sha256_text("ans")
    a = provenance.inputs_sha256({"prompt": "p", "cases": "c", "perturbations": None, "lexicon": "l"})
    assert a == sha256_text("prompt=p\ncases=c\nperturbations=none\nlexicon=l")
    assert a != provenance.inputs_sha256({"prompt": "p", "cases": "c2", "perturbations": None, "lexicon": "l"})


def test_run_records_hashes_and_verifies(tmp_path, sample_cases, sample_perts, lx):
    jobs, prompt = _run(tmp_path, sample_cases, sample_perts, lx)
    man = experiment.read_manifest(tmp_path)
    prov = man["provenance"]
    assert prov["components"]["prompt"] == man["prompt"]["sha256"] and prov["components"]["cases"] == man["inputs"]["cases"]["sha256"]
    assert prov["inputs_sha256"] == provenance.inputs_sha256(prov["components"])
    recs = [json.loads(l) for l in open(tmp_path / "traces.jsonl")]
    assert recs and all(r["provenance"]["prompt_sha256"] and r["provenance"]["answer_sha256"] for r in recs)
    r = recs[0]
    assert r["provenance"]["reasoning_sha256"] == sha256_text(r["reasoning"]) and r["provenance"]["answer_sha256"] == sha256_text(r["answer"])
    # the prompt hash is the hash of exactly what the client was sent: no trace key anywhere in it
    rendered = {j.trace_key: j.rendered for j in jobs}
    user = prompt["user_template"].replace("{case_rendered}", rendered[r["trace_key"]])
    assert r["provenance"]["prompt_sha256"] == provenance.prompt_sha256(prompt["system"], user)
    rep = provenance.verify_run(tmp_path, rendered)
    assert rep["ok"], rep
    c = rep["counts"]
    assert c["traces"] == len(recs) == c["with_provenance"] == c["reasoning_ok"] == c["answer_ok"] == c["prompt_ok"] and c["prompt_unverified"] == 0
    # without the rendered cases the prompts are unverified, not failed
    rep2 = provenance.verify_run(tmp_path)
    assert rep2["ok"] and rep2["counts"]["prompt_unverified"] == len(recs)


def test_verify_detects_edited_trace_and_inputs(tmp_path, sample_cases, sample_perts, lx):
    _run(tmp_path, sample_cases, sample_perts, lx)
    lines = (tmp_path / "traces.jsonl").read_text().splitlines()
    d = json.loads(lines[0])
    d["answer"] = d["answer"] + " (edited)"
    lines[0] = json.dumps(d)
    (tmp_path / "traces.jsonl").write_text("\n".join(lines) + "\n")
    rep = provenance.verify_run(tmp_path)
    assert not rep["ok"] and rep["counts"]["mismatches"] == 1 and rep["mismatches"][0]["field"] == "answer"
    m = experiment.read_manifest(tmp_path)
    m["inputs"]["cases"]["sha256"] = "0" * 64
    experiment.write_manifest(tmp_path, m)
    rep = provenance.verify_run(tmp_path)
    assert any("components differ" in p for p in rep["problems"])


def test_verify_reports_runs_without_provenance(tmp_path, sample_cases, sample_perts, lx):
    _run(tmp_path, sample_cases, sample_perts, lx)
    m = experiment.read_manifest(tmp_path)
    del m["provenance"]
    experiment.write_manifest(tmp_path, m)
    lines = [json.loads(l) for l in (tmp_path / "traces.jsonl").read_text().splitlines()]
    for d in lines:
        d.pop("provenance", None)
    (tmp_path / "traces.jsonl").write_text("\n".join(json.dumps(d) for d in lines) + "\n")
    rep = provenance.verify_run(tmp_path)
    assert not rep["ok"] and len(rep["problems"]) == 2 and all("predates" in p for p in rep["problems"])


def test_error_trace_keeps_prompt_hash(tmp_path, sample_cases, lx):
    from traceaudit.clients.base import ClientError

    def boom(**kw):
        raise ClientError("http", "down", retryable=False)

    client = CallableClient(boom)
    prompt = experiment.load_prompt("enable-v3")
    jobs = experiment.plan(sample_cases[:1], [], ["low"], 1, 0, allow_unreviewed=True, lexicon=lx)
    man = experiment.build_manifest("x", client, prompt, ["low"], 1, 0, None, None, lx, 1, 0, {}, {}, 1)
    experiment.run_experiment(jobs, client, tmp_path, man, prompt, 0, progress=None, sleep=lambda s: None)
    recs = [json.loads(l) for l in open(tmp_path / "traces.jsonl")]
    assert recs[0]["meta"]["error"] and recs[0]["provenance"]["prompt_sha256"] and "answer_sha256" not in recs[0]["provenance"]
    assert provenance.verify_run(tmp_path, {j.trace_key: j.rendered for j in jobs})["ok"]


def test_cli_manifest_verify(tmp_path, sample_cases, sample_perts, lx, capsys):
    from traceaudit.cli import main
    _run(tmp_path, sample_cases, sample_perts, lx)
    assert main(["manifest", "verify", str(tmp_path)]) == 0
    assert main(["manifest", "verify", str(tmp_path), "--cases", str(CASES), "--perturbations", str(PERTS)]) == 0
    err = capsys.readouterr().err
    assert "provenance ok" in err and "0 unverified" in err
    lines = (tmp_path / "traces.jsonl").read_text().splitlines()
    d = json.loads(lines[-1])
    d["reasoning"] = "replaced"
    lines[-1] = json.dumps(d)
    (tmp_path / "traces.jsonl").write_text("\n".join(lines) + "\n")
    assert main(["manifest", "verify", str(tmp_path)]) == 1


def test_ledger_run_verifies_through_cli(tmp_path, capsys):
    """Ledger runs: prompts are rebuilt from the cases, perturbations and recorded render settings."""
    from test_ledger_pipeline import _inputs, _run as ledger_run
    from traceaudit.cli import main
    cases, perts, cp, pp = _inputs(tmp_path)
    _, _, run_dir, _ = ledger_run(tmp_path, cases, perts, cp, pp, runs=1, efforts=("low",))
    man = experiment.read_manifest(run_dir)
    assert man["provenance"]["inputs_sha256"] and man["render"]["evidence_policy"] == "rewrite"
    assert main(["manifest", "verify", str(run_dir), "--cases", str(cp), "--perturbations", str(pp)]) == 0
    err = capsys.readouterr().err
    assert "provenance ok" in err and "0 unverified" in err


def test_import_records_artefact_hash(tmp_path):
    from test_ledger_pipeline import FIX
    from traceaudit import importers, ledger_perturb as LP, ledger_pipeline as PL
    case, trace = importers.load(FIX)
    ex = LP.expectations(case, sources=("reference", "rationale"), rationales=[trace.rationale])
    perts = LP.generate_decisive(case, LP.expectation_lexicon(case, ex), ex)
    run_dir = tmp_path / "imp"
    PL.import_artefacts([FIX], run_dir, [case], perts)
    recs = [json.loads(l) for l in open(run_dir / "traces.jsonl")]
    base = next(r for r in recs if r["variant"] == "base")
    assert base["provenance"]["artefact_sha256"] == sha256_text(FIX.read_text(encoding="utf-8"))
    assert base["provenance"]["answer_sha256"] == sha256_text(base["answer"]) and base["provenance"]["prompt_sha256"] is None
    rep = provenance.verify_run(run_dir)
    assert rep["ok"] and rep["counts"]["prompt_unverified"] == len(recs)
