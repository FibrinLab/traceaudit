"""The text path as an adapter onto the fact ledger (spec 18 §1)."""
from __future__ import annotations

from traceaudit import extract, grounding, ledger, ledger_adapters, perturb, segment
from traceaudit.schema import Trace
from traceaudit.simulate import SimParams, SimulatedModel


def _sim_trace(case, lx, params: SimParams, seed: int = 0, effort: str = "medium") -> Trace:
    key = f"{case.case_id}|base|{effort}|{seed}"
    out = SimulatedModel(params, lx, seed=seed)("", case.render() + f"\n<!-- trace_key: {key} -->", effort, seed)
    return Trace(key, case.case_id, "base", effort, seed, "simulated", out["reasoning"], out["answer"])


def _both_rates(case, lx, params: SimParams, seed: int = 0) -> tuple[float | None, float | None, dict]:
    trace = _sim_trace(case, lx, params, seed)
    claims = segment.segment(trace.reasoning, trace.trace_key, lx)
    rec = grounding.ground(trace, case.truth, claims, extract.finding_spans(case, lx), case.entity, None, lx)
    case_ledger = ledger_adapters.case_to_ledger(case, lx)
    res = ledger.audit(case_ledger, ledger_adapters.trace_to_ledger(trace, claims, lx, case_ledger), lx)
    return rec.grounding_rate, res["metrics"]["grounding_rate"], res


def test_case_to_ledger_facts_match_finding_spans(sample_cases, sample_perts, lx):
    for case in sample_cases:
        spans = extract.finding_spans(case, lx)
        lc = ledger_adapters.case_to_ledger(case, lx)
        patient = [f for f in lc.facts if f.source == "patient"]
        assert len(patient) == sum(len(v) for v in spans.values()) > 0
        assert [f.id for f in patient] == [f"p_{i}" for i in range(1, len(patient) + 1)]
        assert lc.truth == case.entity and lc.candidates == lx.answer_entities() and lc.meta["lexicon_fields"] is True
        # one fact per assertion, in document order, carrying the document's own polarity word and its evidence span
        order = [k for k, _ in case.section_list()]
        positions = [(order.index(lc.meta["spans"][f.id]["report"]), lc.meta["spans"][f.id]["start"]) for f in patient]
        assert positions == sorted(positions)
        by_field: dict[str, list[str]] = {}
        for f in patient:
            sp = lc.meta["spans"][f.id]
            assert f.section == sp["report"] and case.reports[sp["report"]][sp["start"]:sp["end"]] == f.evidence
            assert f.polarity in ("pos", "neg") and f.value in ("Positive", "Negative")
            by_field.setdefault(f.field, []).append(f.polarity)
        assert {k: v[0] for k, v in by_field.items()} == case.truth
        assert not [f for f in lc.facts if f.source == "context"]
    # an authority cue appended to a document becomes a context fact
    pert = next(p for p in sample_perts if p.cue is not None)
    case = next(c for c in sample_cases if c.case_id == pert.case_id)
    variant = perturb.apply(case, pert, lexicon=lx)
    lc = ledger_adapters.case_to_ledger(variant, lx)
    cues = [f for f in lc.facts if f.source == "context"]
    assert len(cues) == 1 and cues[0].id == "c_1" and cues[0].field == ledger_adapters.CUE_FIELD
    assert cues[0].section == pert.cue.report and cues[0].value == lx.entity_display(pert.cue.entity) and cues[0].evidence == pert.cue.text
    sp = lc.meta["spans"]["c_1"]
    assert variant.reports[pert.cue.report][sp["start"]:sp["end"]] == pert.cue.text


def test_truth_overrides_documents(sample_cases, lx):
    case = next(c for c in sample_cases if c.case_id == "CLL-001").copy()
    case.truth = {"CD5": "neg", "CD103": "pos"}  # CD5 disagrees with the documents; CD103 appears in none
    lc = ledger_adapters.case_to_ledger(case, lx, truth_overrides=True)
    cd5 = [f for f in lc.facts if f.field == "CD5"]
    assert cd5 and all(f.value == "Negative" for f in cd5) and lc.meta["stated"][cd5[0].id] == "Positive"
    extra = [f for f in lc.facts if f.field == "CD103"]
    assert len(extra) == 1 and extra[0].value == "Positive" and extra[0].evidence == "" and extra[0].id not in lc.meta["spans"]
    plain = ledger_adapters.case_to_ledger(case, lx)
    assert all(f.value == "Positive" for f in plain.facts if f.field == "CD5") and "stated" not in plain.meta


def test_trace_to_ledger_citations_resolve(sample_cases, lx):
    case = next(c for c in sample_cases if c.case_id == "CLL-001")
    trace = _sim_trace(case, lx, SimParams(p_contradict=0.5), seed=3)
    claims = segment.segment(trace.reasoning, trace.trace_key, lx)
    lc = ledger_adapters.case_to_ledger(case, lx)
    lt = ledger_adapters.trace_to_ledger(trace, claims, lx, lc)
    facts = lc.by_id()
    factual = [c for c in claims if c.type == "factual"]
    assert lt.thinking == trace.reasoning and lt.rationale is None and lt.ablation is None
    assert len(lt.report.sections) == 1 and lt.report.sections[0].title == ledger_adapters.CLAIMS_SECTION
    segs = lt.report.sections[0].segments
    assert [s.text for s in segs] == [c.text for c in factual] and factual
    for seg, claim in zip(segs, factual):
        asserted = {a.finding_id for a in claim.assertions if a.polarity}
        assert seg.citation_ids and all(cid in facts for cid in seg.citation_ids)
        assert {facts[cid].field for cid in seg.citation_ids} == asserted  # every asserted finding cites exactly one fact
        assert len(seg.citation_ids) == len(asserted)
    assert lt.report.decision == grounding.parse_answer(trace.answer, lx).entity == "CLL_SLL"
    assert lt.meta["claims"] == len(claims) and lt.meta["factual_claims"] == len(factual) and lt.meta["hedged"] is False
    # a contradicted claim cites the fact it contradicts, and the ledger grades it as a disagreement
    res = ledger.audit(lc, lt, lx)
    grades = [x["grade"] for s in res["sections"] for seg in s["segments"] for x in seg["cited"]]
    assert "disagree" in grades and "agree" in grades and res["metrics"]["uncited_assertions"] == 0
    assert {c["id"]: c["status"] for c in res["checks"]}["citations_agree"] == "FAIL"
    assert res["thinking"]["candidates"] == ["CLL_SLL"]  # named through the lexicon's entity aliases


def test_grounding_rate_matches_text_path(sample_cases, lx):
    # Clean simulated traces restate findings faithfully: both paths grade everything as grounded.
    for case in sample_cases:
        text_rate, ledger_rate, _ = _both_rates(case, lx, SimParams(), seed=1)
        assert text_rate is not None and ledger_rate is not None
        assert abs(text_rate - ledger_rate) <= 0.05, (case.case_id, text_rate, ledger_rate)
        assert text_rate == 1.0 == ledger_rate
    # With contradictions the units differ (claims vs citations) but the simulator states one finding per sentence,
    # so the rates still agree.
    for case in sample_cases:
        text_rate, ledger_rate, res = _both_rates(case, lx, SimParams(p_contradict=0.4), seed=2)
        assert text_rate < 1.0 and abs(text_rate - ledger_rate) <= 0.05, (case.case_id, text_rate, ledger_rate)
    # Known systematic difference: a fabricated finding (stated in no document) was an *unsupported* claim in the text
    # path and lowered its rate; in the ledger it has no fact to cite, so it is an uncited assertion (and fails
    # `segments_cited`) rather than a graded citation, and the ledger rate ignores it.
    case = sample_cases[0]
    text_rate, ledger_rate, res = _both_rates(case, lx, SimParams(p_fabricate=1.0), seed=4)
    assert text_rate < 1.0 and ledger_rate == 1.0
    assert res["metrics"]["uncited_assertions"] >= 1 and {c["id"]: c["status"] for c in res["checks"]}["segments_cited"] == "FAIL"
