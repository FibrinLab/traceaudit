import pytest

from traceaudit import extract, perturb, schema
from traceaudit.schema import Edit, Perturbation


def test_every_sample_perturbation_satisfies_p1(sample_cases, sample_perts, by_case, lx):
    assert len(sample_perts) >= 25
    for p in sample_perts:
        probs = schema.validate_perturbation(p, by_case[p.case_id], lx)
        assert not probs, [str(x) for x in probs]


def test_apply_is_pure_and_sets_variant(by_case, sample_perts, lx):
    c = by_case["CLL-001"]
    before = c.to_json()
    p = next(p for p in sample_perts if p.case_id == "CLL-001" and p.kind == "decisive")
    v = perturb.apply(c, p, lx)
    assert c.to_json() == before
    assert v.variant == p.variant and v.truth == p.truth_after
    assert v.truth["cyclin_D1"] == "pos" and c.truth["cyclin_D1"] == "neg"


def test_decisive_edits_change_only_edited_findings(by_case, sample_perts, lx):
    for p in sample_perts:
        if p.kind not in ("decisive", "anchor_loss"):
            continue
        c = by_case[p.case_id]
        v = perturb.apply(c, p, lx)
        changed = {k for k in set(c.truth) | set(v.truth) if c.truth.get(k) != v.truth.get(k)}
        assert changed == set(p.edited_findings)
        assert p.primary_finding in changed


@pytest.mark.parametrize("text,fid,to,expect", [
    ("Phenotype: CD5+, CD23+, CD200+.", "CD23", "neg", {"CD5": "pos", "CD23": "neg", "CD200": "pos"}),
    ("Phenotype: CD5 positive, CD23 negative.", "CD23", "pos", {"CD5": "pos", "CD23": "pos"}),
    ("The clonal cells are positive for CD5, CD23 and CD200 and negative for CD10 and FMC7.", "CD23", "neg",
     {"CD5": "pos", "CD200": "pos", "CD10": "neg", "FMC7": "neg", "CD23": "neg"}),
    ("The clonal cells are positive for CD5 and negative for CD10.", "CD5", "neg", {"CD5": "neg", "CD10": "neg"}),
    ("Immunohistochemistry: positive for cyclin D1 and LEF1.", "cyclin_D1", "neg", {"cyclin_D1": "neg", "LEF1": "pos"}),
    ("No t(11;14) CCND1::IGH detected by FISH.", "t_11_14", "pos", {"t_11_14": "pos"}),
    ("t(11;14)(q13;q32) CCND1::IGH detected by FISH.", "t_11_14", "neg", {"t_11_14": "neg"}),
    ("BRAF p.V600E (c.1799T>A) detected (VAF 28%).", "BRAF_V600E", "neg", {"BRAF_V600E": "neg"}),
    ("Smudge cells are frequent.", "smudge_cells", "neg", {"smudge_cells": "neg"}),
    ("Clonal B-cell count 34.2 x10^9/L.", "lymphocytosis", "neg", {"lymphocytosis": "neg"}),
    ("with dim surface immunoglobulin.", "sIg_dim", "neg", {"sIg_dim": "neg"}),
    ("CD20 dim, CD22+.", "CD20_dim", "neg", {"CD20_dim": "neg", "CD22": "pos"}),
    ("CD79b dim, CD5+.", "CD79b", "neg", {"CD79b": "neg", "CD5": "pos"}),
])
def test_plan_flip_surface_forms(lx, text, fid, to, expect):
    rws = perturb.plan_flip(text, fid, to, lx)
    out = perturb.apply_rewrites(text, rws)
    assert extract.findings(out, lx) == expect, out


def test_plan_flip_errors(lx):
    with pytest.raises(perturb.PerturbationError):
        perturb.plan_flip("CD5 positive.", "CD23", "neg", lx)
    with pytest.raises(perturb.PerturbationError):
        perturb.plan_flip("CD5 positive.", "CD5", "pos", lx)
    with pytest.raises(perturb.PerturbationError):
        perturb.plan_flip("We considered CD5 here.", "CD5", "neg", lx)


def test_apply_detects_truth_after_mismatch(by_case, lx):
    c = by_case["CLL-001"]
    p = Perturbation("x", c.case_id, "dec-cd23", "decisive", edits=[Edit("CD23", "pos", "neg", "primary")], primary_finding="CD23",
                     truth_after={**c.truth, "CD23": "neg", "CD5": "neg"})
    with pytest.raises(perturb.PerturbationError):
        perturb.apply(c, p, lx, verify=True)


def test_neutral_keeps_truth_and_records_ops(sample_cases, lx):
    for c in sample_cases:
        ps = perturb.generate_neutral(c, 1, lx)
        assert ps and ps[0].kind == "neutral"
        v = perturb.apply(c, ps[0], lx)
        assert v.truth == c.truth
        assert all(e.op for e in ps[0].edits) and all(e.finding_id is None for e in ps[0].edits)
        assert v.render() != c.render()


def test_authority_cue_appended_to_clinical(by_case, lx):
    c = by_case["FL-001"]
    ps = perturb.generate_authority(c, lx)
    wrong = next(p for p in ps if not p.cue.correct)
    assert wrong.cue.entity == lx.wrong_cues("FL")[0]
    v = perturb.apply(c, wrong, lx)
    assert v.reports["clinical"].endswith(wrong.cue.text) and v.truth == c.truth
    right = next(p for p in ps if p.cue.correct)
    assert right.variant == "auth-right" and right.cue.entity == "FL"


def test_decisive_catalogue_preconditions(lx):
    from traceaudit.domains.haematology import casegen
    for ent in casegen.CASE_PREFIX:
        c = casegen.generate_case(ent, 1, 20261020, lx)
        for p in perturb.generate_decisive(c, lx):
            assert p.expected_entity != c.entity
            assert c.truth[p.primary_finding] != p.truth_after[p.primary_finding]


def test_generation_is_deterministic(by_case, lx):
    c = by_case["MZL-001"]
    a = [p.to_json() for p in perturb.generate_all(c, 5, lx, include_right=True)]
    b = [p.to_json() for p in perturb.generate_all(c, 5, lx, include_right=True)]
    assert a == b
