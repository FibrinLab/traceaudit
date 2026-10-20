import pytest

from traceaudit import schema
from traceaudit.schema import Case, Claim, Perturbation, Trace, make_trace_key, parse_trace_key, variant_kind


def test_trace_key_roundtrip():
    k = make_trace_key("CLL-001", "dec-cyclin_d1", "high", 3)
    assert k == "CLL-001|dec-cyclin_d1|high|3"
    assert parse_trace_key(k) == ("CLL-001", "dec-cyclin_d1", "high", 3)
    with pytest.raises(ValueError):
        make_trace_key("a|b", "base", "low", 0)
    with pytest.raises(ValueError):
        parse_trace_key("x|y")


def test_variant_kind():
    assert variant_kind("base") == "base"
    assert variant_kind("dec-x") == "decisive"
    assert variant_kind("neu-1") == "neutral"
    assert variant_kind("anc-x") == "anchor_loss"
    assert variant_kind("auth-right") == "authority"


def test_case_roundtrip_preserves_unknown_keys(sample_cases):
    c = sample_cases[0]
    d = c.to_dict()
    d["future_field"] = {"x": 1}
    c2 = Case.from_dict(d)
    assert c2.to_dict()["future_field"] == {"x": 1}
    assert Case.from_json(c.to_json()) == c


def test_render_order_and_missing(sample_cases):
    c = sample_cases[0].copy()
    c.reports["molecular"] = ""
    r = c.render()
    assert r.index("## Clinical summary") < r.index("## Morphology") < r.index("## Flow cytometry") < r.index("## Cytogenetics") < r.index("## Molecular")
    assert r.rstrip().endswith("Not performed.")
    offs = c.report_offsets()
    assert r[offs["morphology"]:offs["morphology"] + 10] == c.reports["morphology"][:10]


def test_newer_schema_version_rejected():
    with pytest.raises(ValueError):
        Trace.from_dict({"schema_version": 99, "trace_key": "a|b|low|0", "case_id": "a", "variant": "b", "effort": "low", "run": 0,
                         "model": "m", "reasoning": "", "answer": ""})


def test_validate_case_codes(sample_cases, lx):
    c = sample_cases[0].copy()
    assert schema.validate_case(c, lx) == []
    c.truth["CD5"] = "neg" if c.truth["CD5"] == "pos" else "pos"
    codes = {p.code for p in schema.validate_case(c, lx)}
    assert "C1_TRUTH_MISMATCH" in codes
    c2 = sample_cases[0].copy()
    c2.reports["flow_cytometry"] += " CD5 negative." if c2.truth["CD5"] == "pos" else " CD5 positive."
    assert "C2_POLARITY_CONFLICT" in {p.code for p in schema.validate_case(c2, lx)}
    c3 = sample_cases[0].copy()
    c3.case_id = "bad"
    assert "C3_BAD_ID" in {p.code for p in schema.validate_case(c3, lx)}
    for code in schema.PROBLEM_CODES:
        assert code.split("_")[0][0] in "CPT"


def test_claim_roundtrip():
    from traceaudit.schema import Assertion
    cl = Claim("k", 0, 0, 0, 5, "CD5+.", "factual", assertions=[Assertion("CD5", "pos", 0, 3, "CD5+", 3, 4, "suffix")])
    cl2 = Claim.from_json(cl.to_json())
    assert cl2.assertions[0].finding_id == "CD5" and cl2.assertions[0].polarity == "pos"


def test_edit_from_key_serialises_as_from():
    p = Perturbation("c/v", "c", "dec-x", "decisive", edits=[schema.Edit("CD5", "neg", "pos", "primary")])
    d = p.to_dict()
    assert d["edits"][0]["from"] == "neg" and "from_" not in d["edits"][0]
    assert Perturbation.from_dict(d).edits[0].from_ == "neg"
