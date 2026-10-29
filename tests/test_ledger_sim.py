import json

from traceaudit import ledger, ledger_io, ledger_perturb as LP, ledger_synth
from traceaudit.ledger_sim import LedgerSimParams, LedgerSimulatedModel


def _case():
    return ledger_synth.generate_set(1, 0)[0]


def _call(sim, case, variant="base", effort="medium", meta=None, pert=None):
    v = LP.apply(case, pert) if pert is not None else case
    m = {"trace_key": f"{case.case_id}|{variant}|{effort}|0", "kind": "base", "base_entity": case.truth, **(meta or {})}
    out = sim("sys", ledger_io.render_case(v), effort, 1, meta=m)
    lt, w = ledger_io.parse_output(out["answer"], v, out["reasoning"])
    return v, lt, w, out


def test_clean_sim_parses_and_audits_clean():
    case = _case()
    sim = LedgerSimulatedModel(LedgerSimParams(), seed=3)
    for effort in ("low", "medium", "high"):
        v, lt, w, out = _call(sim, case, effort=effort)
        assert w == [] and lt.report.contract_valid and lt.report.decision == case.truth
        res = ledger.audit(v, lt)
        status = {c["id"]: c["status"] for c in res["checks"]}
        assert res["metrics"]["cited_disagree"] == 0 and status["citations_exist"] == "PASS" and status["thinking_considers_alternatives"] == "PASS"
        assert status["one_favoured"] == "PASS" and status["differential_complete"] == "PASS" and status["thinking_agrees"] == "PASS"
    # a fenced and a bare JSON reply both occur
    answers = {_call(LedgerSimulatedModel(LedgerSimParams(), seed=s), case)[3]["answer"].startswith("```") for s in range(6)}
    assert answers == {True, False}


def test_sim_reads_edit_from_prompt_and_discloses():
    case = _case()
    ex = LP.expectations(case, sources=("structured",))
    pert = LP.generate_decisive(case, LP.expectation_lexicon(case, ex), ex)[0]
    sim = LedgerSimulatedModel(LedgerSimParams(), seed=1)
    meta = {"kind": "decisive", "expected_entity": pert.expected_entity, "primary_finding": pert.primary_finding, "co_edits": pert.co_edits,
            "linked_findings": pert.linked_findings}
    v, lt, w, out = _call(sim, case, pert.variant, meta=meta, pert=pert)
    assert lt.report.decision == pert.expected_entity
    f = v.fact(pert.primary_finding)
    assert f"({pert.primary_finding})" in out["reasoning"] and f.value.lower() in out["reasoning"].lower()


def test_faults_one_at_a_time():
    case = _case()
    ex = LP.expectations(case, sources=("structured",))
    pert = LP.generate_decisive(case, LP.expectation_lexicon(case, ex), ex)[0]
    dec_meta = {"kind": "decisive", "expected_entity": pert.expected_entity, "primary_finding": pert.primary_finding, "co_edits": pert.co_edits}
    v, lt, _, out = _call(LedgerSimulatedModel(LedgerSimParams(p_silent=1.0), seed=1), case, pert.variant, meta=dec_meta, pert=pert)
    assert lt.report.decision == pert.expected_entity and pert.primary_finding not in out["reasoning"] and pert.primary_finding not in out["answer"]
    v, lt, _, _ = _call(LedgerSimulatedModel(LedgerSimParams(p_miss=1.0), seed=1), case, pert.variant, meta=dec_meta, pert=pert)
    assert lt.report.decision == case.truth
    v, lt, _, _ = _call(LedgerSimulatedModel(LedgerSimParams(p_contradict=1.0), seed=1), case)
    assert ledger.audit(v, lt)["metrics"]["cited_disagree"] > 0
    v, lt, w, _ = _call(LedgerSimulatedModel(LedgerSimParams(p_fabricate=1.0), seed=1), case)
    assert "UNKNOWN_IDS" in w and not lt.report.contract_valid
    v, lt, _, _ = _call(LedgerSimulatedModel(LedgerSimParams(), seed=1), case, "anc-f2", meta={"kind": "anchor_loss"})
    pa, sig = ledger_io.ledger_answer(lt, v)
    assert pa.hedged and sig["confidence_low"] and sig["status"]
    v, lt, _, _ = _call(LedgerSimulatedModel(LedgerSimParams(p_unhedged=1.0), seed=1), case, "anc-f2", meta={"kind": "anchor_loss"})
    assert not ledger_io.ledger_answer(lt, v)[0].hedged
    v, lt, _, _ = _call(LedgerSimulatedModel(LedgerSimParams(p_spurious=1.0), seed=1), case, "neu-1", meta={"kind": "neutral"})
    assert lt.report.decision != case.truth
    au = {"kind": "authority", "cue_entity": "K3", "cue_fact": "c_3"}
    v, lt, _, out = _call(LedgerSimulatedModel(LedgerSimParams(p_shift_ack=1.0), seed=1), case, "auth-wrong-k3", meta=au)
    assert lt.report.decision == "K3" and "c_3" in out["reasoning"] and any("c_3" in g.citation_ids for s in lt.report.sections for g in s.segments)
    v, lt, _, out = _call(LedgerSimulatedModel(LedgerSimParams(p_shift_silent=1.0), seed=1), case, "auth-wrong-k3", meta=au)
    assert lt.report.decision == "K3" and "c_3" not in out["reasoning"] and "referring" not in out["reasoning"].lower()
    ab = {"kind": "ablation", "decision_before": case.truth}
    v, lt, _, _ = _call(LedgerSimulatedModel(LedgerSimParams(), seed=1), case, "abl-medium-r0", meta=ab)
    assert lt.report.decision != case.truth
    v, lt, _, _ = _call(LedgerSimulatedModel(LedgerSimParams(p_ablation_ignored=1.0), seed=1), case, "abl-medium-r0", meta=ab)
    assert lt.report.decision == case.truth
    v, lt, w, out = _call(LedgerSimulatedModel(LedgerSimParams(p_contract_break=1.0), seed=1), case)
    assert "NO_JSON" in w and lt.meta["parse_mode"] == "text_fallback" and lt.report.decision == case.truth and out["answer"].startswith("Decision:")
    v, lt, _, _ = _call(LedgerSimulatedModel(LedgerSimParams(p_trace_answer_mismatch=1.0), seed=1), case)
    assert lt.rationale.decision == lt.report.decision  # the contract's rationale carries the report decision; the favoured entry differs
    assert [d.diagnosis for d in lt.rationale.differential if d.verdict == "favoured"] != [lt.report.decision]


def test_uniform_params_cover_new_fields():
    p = LedgerSimParams.uniform(0.1, p_base_noise=0.0)
    assert p.p_contract_break == 0.1 and p.p_ablation_ignored == 0.1 and p.p_silent == 0.1 and p.p_base_noise == 0.0
    assert json.dumps(p.__dict__)
