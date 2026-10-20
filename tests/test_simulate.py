from traceaudit import extract, grounding, perturb, probes, segment
from traceaudit.probes import BaseRef
from traceaudit.schema import Trace
from traceaudit.simulate import SimParams, SimulatedModel, nearest_entity


def test_nearest_entity(lx):
    assert nearest_entity({"CD5": "pos", "CD23": "pos", "CD200": "pos", "cyclin_D1": "neg"}, lx) == "CLL_SLL"
    assert nearest_entity({"CD5": "pos", "CD23": "neg", "cyclin_D1": "pos", "t_11_14": "pos"}, lx) == "MCL"
    assert nearest_entity({"BRAF_V600E": "pos", "CD103": "pos", "CD25": "pos", "hairy_cells": "pos"}, lx) == "HCL"


def _call(sim, case, variant, key, meta):
    out = sim("sys", variant.render() + f"\n<!-- trace_key: {key} -->", key.split("|")[2], 1, meta=meta)
    cid, var, eff, run = key.split("|")
    t = Trace(key, cid, var, eff, int(run), "sim", out["reasoning"], out["answer"])
    return t, segment.segment(out["reasoning"], key, lx_global)


lx_global = None


def test_clean_simulator_is_perfectly_grounded_and_faithful(lx, by_case, sample_perts):
    global lx_global
    lx_global = lx
    sim = SimulatedModel(SimParams(), lx, seed=3)
    c = by_case["CLL-001"]
    for eff in ("low", "medium", "high"):
        t, claims = _call(sim, c, c, f"CLL-001|base|{eff}|0", {"kind": "base", "base_entity": c.entity})
        rec = grounding.ground(t, c.truth, claims, extract.finding_spans(c, lx), c.entity, None, lx)
        assert rec.n_contradicted == 0 and rec.n_unsupported == 0 and rec.answer_entity == "CLL_SLL"
    p = next(p for p in sample_perts if p.case_id == "CLL-001" and p.kind == "decisive")
    v = perturb.apply(c, p, lx)
    meta = {"kind": "decisive", "base_entity": c.entity, "primary_finding": p.primary_finding, "co_edits": p.co_edits,
            "linked_findings": p.linked_findings, "expected_entity": p.expected_entity}
    for run in range(5):
        t, claims = _call(sim, c, v, f"CLL-001|{p.variant}|low|{run}", meta)
        rec = probes.score_counterfactual(t, p, BaseRef("CLL-001", "low", "CLL_SLL", 1.0, True, 3), claims, None, lx)
        assert rec.outcome == "disclosed"


def _rate(lx, by_case, sample_perts, params, kind, outcome_fn, n=60):
    global lx_global
    lx_global = lx
    sim = SimulatedModel(params, lx, seed=11)
    c = by_case["CLL-001"]
    p = next(p for p in sample_perts if p.case_id == "CLL-001" and p.kind == kind)
    v = perturb.apply(c, p, lx)
    meta = {"kind": kind, "base_entity": c.entity, "primary_finding": p.primary_finding, "co_edits": p.co_edits,
            "linked_findings": p.linked_findings, "expected_entity": p.expected_entity}
    hits = 0
    for run in range(n):
        t, claims = _call(sim, c, v, f"CLL-001|{p.variant}|medium|{run}", meta)
        hits += outcome_fn(t, claims, p)
    return hits / n


def test_faults_one_at_a_time(lx, by_case, sample_perts):
    ref = BaseRef("CLL-001", "medium", "CLL_SLL", 1.0, True, 3)
    silent = _rate(lx, by_case, sample_perts, SimParams(p_silent=1.0), "decisive",
                   lambda t, cl, p: probes.score_counterfactual(t, p, ref, cl, None, lx).outcome == "silent")
    assert silent == 1.0
    missed = _rate(lx, by_case, sample_perts, SimParams(p_miss=1.0), "decisive",
                   lambda t, cl, p: probes.score_counterfactual(t, p, ref, cl, None, lx).outcome == "missed")
    assert missed == 1.0
    linked = _rate(lx, by_case, sample_perts, SimParams(p_mention_linked_only=1.0), "decisive",
                   lambda t, cl, p: (lambda r: r.outcome == "silent" and r.mentioned_any)(probes.score_counterfactual(t, p, ref, cl, None, lx)))
    assert linked == 1.0
    spurious = _rate(lx, by_case, sample_perts, SimParams(p_spurious=1.0), "neutral",
                     lambda t, cl, p: probes.score_counterfactual(t, p, ref, cl, None, lx).outcome == "spurious")
    assert spurious == 1.0
    unhedged = _rate(lx, by_case, sample_perts, SimParams(p_unhedged=1.0), "anchor_loss",
                     lambda t, cl, p: probes.score_counterfactual(t, p, ref, cl, None, lx).outcome == "unhedged")
    assert unhedged == 1.0
    c = by_case["CLL-001"]
    contr = _rate(lx, by_case, sample_perts, SimParams(p_contradict=1.0), "neutral",
                  lambda t, cl, p: grounding.ground(t, perturb.apply(c, p, lx).truth, cl, {}, None, None, lx).n_contradicted > 0)
    assert contr == 1.0
    fab = _rate(lx, by_case, sample_perts, SimParams(p_fabricate=1.0), "neutral",
                lambda t, cl, p: grounding.ground(t, perturb.apply(c, p, lx).truth, cl, {}, None, None, lx).n_unsupported > 0)
    assert fab == 1.0


def test_authority_faults(lx, by_case, sample_perts):
    global lx_global
    lx_global = lx
    c = by_case["CLL-001"]
    p = next(p for p in sample_perts if p.case_id == "CLL-001" and p.variant.startswith("auth-wrong"))
    v = perturb.apply(c, p, lx)
    ref = BaseRef("CLL-001", "medium", "CLL_SLL", 1.0, True, 3)
    for params, expected in ((SimParams(p_shift_silent=1.0), "shifted_silent"), (SimParams(p_shift_ack=1.0), "shifted_ack"), (SimParams(), "held")):
        sim = SimulatedModel(params, lx, seed=5)
        t, claims = _call(sim, c, v, f"CLL-001|{p.variant}|medium|0", {"kind": "authority", "base_entity": c.entity})
        assert probes.score_authority(t, p, ref, claims, None, lx).outcome == expected


def test_styles_segment_cleanly(lx, by_case):
    global lx_global
    lx_global = lx
    c = by_case["MCL-001"]
    for style in ("plain", "arrows", "bullets"):
        sim = SimulatedModel(SimParams(style=style), lx, seed=1)
        t, claims = _call(sim, c, c, "MCL-001|base|high|0", {"kind": "base", "base_entity": "MCL"})
        rec = grounding.ground(t, c.truth, claims, {}, "MCL", None, lx)
        assert rec.n_contradicted == 0 and rec.n_unsupported == 0 and rec.n_factual >= 5, style
