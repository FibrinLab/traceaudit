"""Golden scores for the packaged sample under the clean simulator; regenerate with --update-golden."""
import json
from pathlib import Path

import pytest

from traceaudit import experiment, lexicon, pipeline
from traceaudit.clients import make_client
from traceaudit.schema import load_cases, load_perturbations
from traceaudit.simulate import SimParams

GOLDEN = Path(__file__).with_name("golden") / "sample_scores.json"
PKG = Path(__file__).resolve().parents[1] / "traceaudit" / "domains" / "haematology"



def _scores(tmp_path):
    lx = lexicon.load()
    cases = load_cases(PKG / "sample_cases.jsonl")
    perts = load_perturbations(PKG / "sample_perturbations.jsonl")
    client = make_client("sim", "simulated", params=SimParams.uniform(0.3, p_base_noise=0.0, p_trace_answer_mismatch=0.0), seed=1)
    prompt = experiment.load_prompt("enable-v3")
    jobs = experiment.plan(cases, perts, ("low", "high"), 2, 1, lexicon=lx, right_cue_fraction=1.0)
    man = experiment.build_manifest("golden", client, prompt, ["low", "high"], 2, 1, None, None, lx, 6, len(perts), {}, {}, 1)
    experiment.run_experiment(jobs, client, tmp_path, man, prompt, 1)
    pipeline.score_all(tmp_path, cases, perts, "D1", "lexical", 100, 1, lx)
    g = [json.loads(l) for l in open(tmp_path / "grounding.jsonl")]
    cf = [json.loads(l) for l in open(tmp_path / "counterfactual.jsonl")]
    au = [json.loads(l) for l in open(tmp_path / "authority.jsonl")]
    return {"grounding": {r["trace_key"]: [r["n_factual"], r["n_supported"], r["n_contradicted"], r["n_unsupported"], r["answer_entity"]] for r in g},
            "counterfactual": {r["trace_key"]: r["outcome"] for r in cf}, "authority": {r["trace_key"]: r["outcome"] for r in au}}


def test_golden(tmp_path, request):
    got = _scores(tmp_path)
    if request.config.getoption("--update-golden", default=False) or not GOLDEN.exists():
        GOLDEN.parent.mkdir(exist_ok=True)
        GOLDEN.write_text(json.dumps(got, indent=1, sort_keys=True))
        pytest.skip("golden file written")
    want = json.loads(GOLDEN.read_text())
    assert got == want
