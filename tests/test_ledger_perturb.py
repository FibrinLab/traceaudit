from pathlib import Path

import pytest

from traceaudit import importers, ledger_io, ledger_perturb as LP
from traceaudit.ledger import Fact, LedgerCase
from traceaudit.schema import VARIANT_RE, variant_kind

FIX = Path(__file__).with_name("fixtures") / "enable_trace_case_003.md"


def synth_case() -> LedgerCase:
    """A domain-free case with structured criteria: A expects x+ y+ z-, B expects x- y+ w+, C expects z+ w-."""
    facts = [Fact("p_1", "patient", "signals", "x", "Positive", "x is positive"), Fact("p_2", "patient", "signals", "y", "Positive", "y positive"),
             Fact("p_3", "patient", "signals", "z", "Negative", "no z"), Fact("p_4", "patient", "other", "w", "Negative", "w absent"),
             Fact("p_5", "patient", "other", "q", "Not performed", ""), Fact("c_1", "context", "ticket", "priority", "High", ""),
             Fact("w_1", "who", "A", "essential_criteria", "x positive and y positive", "", "A")]
    meta = {"criteria": [
        {"candidate": "A", "criterion": "x and y", "strength": "essential", "reference_ids": ["w_1"], "expect": [{"field": "x", "value": "pos"}, {"field": "y", "value": "pos"}]},
        {"candidate": "A", "criterion": "no z", "strength": "desirable", "expect": [{"field": "z", "value": "neg"}]},
        {"candidate": "B", "criterion": "x negative", "strength": "essential", "expect": [{"field": "x", "value": "neg"}, {"field": "y", "value": "pos"}]},
        {"candidate": "B", "criterion": "w", "strength": "desirable", "expect": [{"field": "w", "value": "pos"}]},
        {"candidate": "C", "criterion": "z", "strength": "essential", "expect": [{"field": "z", "value": "pos"}, {"field": "w", "value": "neg"}]},
    ]}
    return LedgerCase("S-001", "A", ["A", "B", "C"], facts, {f.id for f in facts}, meta)


def test_flip_value_vocabulary():
    assert LP.flip_value("Positive") == "Negative" and LP.flip_value("ABSENT") == "PRESENT" and LP.flip_value("Weak") == "Negative"
    assert LP.flip_value("132") is None and LP.flip_value("unmutated") is None and LP.flip_value("Not detected") == "Detected"


def test_expectations_from_structured_reference_and_rationale():
    case = synth_case()
    ex = LP.expectations(case, sources=("structured",))
    assert {(e.candidate, e.field, e.expected, e.strength) for e in ex} >= {("A", "x", "pos", "essential"), ("B", "w", "pos", "desirable"), ("C", "z", "pos", "essential")}
    ex_ref = LP.expectations(case, sources=("reference",))
    assert {(e.candidate, e.field, e.expected) for e in ex_ref} == {("A", "x", "pos"), ("A", "y", "pos")} and all(e.origin == "reference_text" for e in ex_ref)
    fcase, trace = importers.load(FIX)
    ref = {(e.candidate, e.field, e.expected) for e in LP.expectations(fcase, sources=("reference",))}
    assert ("SMZL", "CD5", "neg") in ref and ("MCL", "CD5", "pos") in ref and not any(c == "CLL/SLL" for c, _, _ in ref)
    rat = LP.expectations(fcase, sources=("rationale",), rationales=[trace.rationale])
    assert all(e.model_derived for e in rat)
    assert {(e.candidate, e.field, e.expected) for e in rat} >= {("FL", "CD10", "pos"), ("SMZL", "CD5", "neg"), ("CLL/SLL", "CD5", "pos")}


def test_expectation_lexicon_fills_discriminators_and_linked():
    case = synth_case()
    lx = LP.expectation_lexicon(case, LP.expectations(case, sources=("structured",)))
    assert lx.discriminators["x"] == {"A": "pos", "B": "neg"} and lx.linked["x"] == ["y"]
    assert LP.table_candidates(lx) == ["A", "B", "C"] and lx.nearest_entity(LP.found_map(case), ["A", "B", "C"]) == "A"


def test_decisive_criteria_search_synth():
    case = synth_case()
    ex = LP.expectations(case, sources=("structured",))
    lx = LP.expectation_lexicon(case, ex)
    perts = LP.generate_decisive(case, lx, ex)
    # C is one flip away (z), B needs two (x and w): the search ranks by flips first
    assert [p.variant for p in perts] == ["dec-z", "dec-x"]
    c = perts[0]
    assert c.expected_entity == "C" and VARIANT_RE.match(c.variant) and variant_kind(c.variant) == "decisive"
    assert [(e.finding_id, e.from_, e.to, e.value_after, e.role) for e in c.edits] == [("p_3", "neg", "pos", "Positive", "primary")]
    assert c.linked_findings == ["p_4"] and c.flags == [] and c.extra["base_candidate"] == "A"
    assert c.truth_after == {"x": "pos", "y": "pos", "z": "pos", "w": "neg", "priority": "pos"}
    v = LP.apply(case, c)
    assert v.truth == "C" and LP.strict_nearest(lx, LP.found_map(v), ["A", "B", "C"]) == "C"
    b = perts[1]
    assert b.expected_entity == "B" and "multi_fact" in b.flags and {e.extra["field"] for e in b.edits} == {"x", "w"}
    assert [e.role for e in b.edits] == ["primary", "co_edit"] and b.primary_finding == "p_1" and b.linked_findings == ["p_2"]


def test_decisive_target_must_expect_new_value_and_base_recovered():
    case = synth_case()
    # a sparse candidate that expects nothing cannot "win" by someone else's flip
    case.meta["criteria"].append({"candidate": "D", "criterion": "nothing", "expect": []})
    case.candidates.append("D")
    ex = LP.expectations(case, sources=("structured",))
    lx = LP.expectation_lexicon(case, ex)
    assert all(p.expected_entity != "D" for p in LP.generate_decisive(case, lx, ex))
    # when the table does not recover the base candidate, nothing is proposed and the log says why
    broken = synth_case()
    broken.truth = "C"
    ex = LP.expectations(broken, sources=("structured",))
    lx = LP.expectation_lexicon(broken, ex)
    assert LP.generate_decisive(broken, lx, ex) == [] and any("does not recover" in m for m in LP.generation_log())


def test_decisive_fixture_rationale_gives_cd5_pair_to_smzl():
    case, trace = importers.load(FIX)
    ex = LP.expectations(case, sources=("reference", "rationale"), rationales=[trace.rationale])
    lx = LP.expectation_lexicon(case, ex)
    perts = LP.generate_decisive(case, lx, ex)
    smzl = next(p for p in perts if p.expected_entity == "SMZL")
    assert smzl.variant == "dec-cd5" and "model_derived" in smzl.flags and {e.extra["field"] for e in smzl.edits} == {"CD5", "paraprotein"}
    v = LP.apply(case, smzl)
    assert v.fact("p_1").value == "Negative" and v.fact("c_109").value == "Present" and v.truth == "SMZL"
    # cumulative snippets no longer assert CD5 positive
    assert "CD5 negative" in v.fact("p_6").evidence and LP.verify(case, v, smzl) == []
    assert any(f.startswith("evidence_rewritten:") for f in v.meta["flags"])


def test_anchor_untest_keeps_base_nearest_and_section_drop_fallback():
    case = synth_case()
    ex = LP.expectations(case, sources=("structured",))
    lx = LP.expectation_lexicon(case, ex)
    [anc] = LP.generate_anchor_loss(case, lx)
    assert anc.variant in ("anc-x", "anc-y") and anc.expected_behaviour == "hedge" and anc.edits[0].op == "untest"
    v = LP.apply(case, anc)
    assert v.fact(anc.primary_finding).value == "Not performed" and v.truth is None
    assert LP.strict_nearest(lx, LP.found_map(v), ["A", "B", "C"]) == "A"
    [flip] = LP.generate_anchor_loss(case, lx, op="flip")
    assert flip.edits[0].to == "neg" and flip.truth_after[flip.edits[0].extra["field"]] == "neg"
    bare = LedgerCase("S-002", "A", ["A", "B"], [Fact("p_1", "patient", "s1", "x", "Positive"), Fact("p_2", "patient", "s1", "y", "Positive"),
                                                 Fact("p_3", "patient", "s2", "z", "Negative")])
    [drop] = LP.generate_anchor_loss(bare, LP.expectation_lexicon(bare, []))
    assert drop.variant == "anc-drop-s2" and "section_drop" in drop.flags and LP.apply(bare, drop).fact("p_3").value == "Not performed"


def test_neutral_multiset_and_id_map():
    case, _ = importers.load(FIX)
    [neu] = LP.generate_neutral(case, 7)
    ops = [e.op for e in neu.edits]
    assert neu.variant == "neu-1" and 1 <= len(ops) <= 4 and len(set(ops)) == len(ops)
    v = LP.apply(case, neu)
    assert LP.informative_multiset(v) == LP.informative_multiset(case) and LP.verify(case, v, neu) == []
    again = LP.generate_neutral(case, 7)[0]
    assert [e.op for e in again.edits] == ops and [e.extra for e in again.edits] == [e.extra for e in neu.edits]
    [ren] = LP.generate_neutral(case, 7, ops=("renumber_ids",))
    m = ren.edits[0].extra["id_map"]
    v = LP.apply(case, ren)
    assert sorted(m) == sorted(m.values()) and v.fact(m["p_1"]).field == "CD5" and v.allowed_ids == case.allowed_ids


def test_authority_cue_is_one_context_fact():
    case = synth_case()
    lx = LP.expectation_lexicon(case, LP.expectations(case, sources=("structured",)))
    perts = LP.generate_authority(case, lx)
    # the wrong cue is the runner-up by table score (C is one flip from the base; B is two)
    assert [p.variant for p in perts] == ["auth-wrong-c", "auth-right"] and perts[0].cue.entity == "C" and perts[1].cue.correct
    v = LP.apply(case, perts[0])
    assert len(v.facts) == len(case.facts) + 1 and v.fact("c_2").field == LP.CUE_FIELD and v.fact("c_2").value == "C" and "working diagnosis" in v.fact("c_2").evidence
    assert LP.verify(case, v, perts[0]) == [] and v.truth == "A"
    assert [p.variant for p in LP.generate_authority(case, lx, include_right=False)] == ["auth-wrong-c"]


def test_ablation_plan_and_modes():
    case, trace = importers.load(FIX)
    ids = [i for d in trace.rationale.discriminators for i in d["ids"]]
    abl = LP.plan_ablation(case, ids, "medium", 0, "CLL/SLL", False, "case_003|base|medium|0")
    assert abl.variant == "abl-medium-r0" and abl.kind == "ablation" and variant_kind(abl.variant) == "ablation"
    assert abl.primary_finding == "p_1" and abl.co_edits == ["p_4", "p_23", "p_55", "p_57"] and abl.extra["decision_before"] == "CLL/SLL"
    v = LP.apply(case, abl)
    assert len(v.facts) == len(case.facts) - 5 and "p_1" not in v.allowed_ids and v.truth is None and LP.verify(case, v, abl) == []
    masked = LP.plan_ablation(case, ids, "medium", 0, "CLL/SLL", False, None, mode="mask")
    assert LP.apply(case, masked).fact("p_1").value == "Not performed"
    assert LP.plan_ablation(case, ["w_62", "nope"], "low", 0, None, None, None) is None


def test_apply_is_pure_and_verify_detects_tampering():
    case = synth_case()
    ex = LP.expectations(case, sources=("structured",))
    lx = LP.expectation_lexicon(case, ex)
    pert = LP.generate_decisive(case, lx, ex)[0]
    before = ledger_io.case_to_dict(case)
    v = LP.apply(case, pert)
    assert ledger_io.case_to_dict(case) == before
    v.fact("p_2").value = "Negative"
    assert "P1_LEDGER_UNEXPECTED_CHANGE:p_2" in LP.verify(case, v, pert)
    v.facts.append(Fact("p_9", "patient", "signals", "extra", "Positive"))
    assert "P1_LEDGER_UNEXPECTED_FACT:p_9" in LP.verify(case, v, pert)
    v.fact("p_3").evidence = "no z"
    assert any(p.startswith("P1_LEDGER_EVIDENCE_OLD_VALUE:p_3") for p in LP.verify(case, v, pert))


def test_evidence_policies():
    case = synth_case()
    ex = LP.expectations(case, sources=("structured",))
    lx = LP.expectation_lexicon(case, ex)
    pert = LP.generate_decisive(case, lx, ex)[0]
    assert LP.apply(case, pert, evidence_policy="redact").fact("p_3").evidence == ""
    v = LP.apply(case, pert, evidence_policy="synthesize")
    assert v.fact("p_3").evidence == "z Positive" and any(f.startswith("evidence_synthesized:p_3") for f in v.meta["flags"])


def test_generate_all_and_export(tmp_path):
    case = synth_case()
    perts = LP.generate_all(case, 3, include_right=True)
    kinds = [p.kind for p in perts]
    assert kinds.count("decisive") == 2 and kinds.count("neutral") == 1 and kinds.count("anchor_loss") == 1 and kinds.count("authority") == 2
    assert len({p.variant for p in perts}) == len(perts)
    index = LP.export_variants([case], perts, tmp_path)
    assert [r["variant"] for r in index] == ["base"] + [p.variant for p in perts]
    base_rec = index[0]
    back, _ = importers.parse_markdown(Path(base_rec["md"]).read_text())
    assert ledger_io.fact_fingerprint(back) == base_rec["fingerprint"]
    assert (tmp_path / "index.jsonl").exists() and Path(index[1]["json"]).exists()
    with pytest.raises(ValueError):
        LP._mk(case, "decisive", "bad variant", [])
