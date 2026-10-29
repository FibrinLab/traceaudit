import json
from pathlib import Path

from traceaudit import importers, ledger_io
from traceaudit.ledger import LedgerCase, Fact

FIX = Path(__file__).with_name("fixtures") / "synthetic_trace_SYN-003.md"


def _good(case):
    return {"decision": "K1", "decision_status": "definitive", "confidence": "high",
            "report": {"sections": [{"title": "Summary", "segments": [{"text": "mk1 positive, mk4 positive.", "citation_ids": ["p_1", "p_4"]}]}]},
            "differential": [{"diagnosis": c, "verdict": "favoured" if c == "K1" else "unlikely", "supporting": ["p_1"], "contradicting": [],
                              "rationale": "x", "criteria": [{"criterion": "mk1+", "status": "met", "ids": ["p_1"]}]} for c in case.candidates],
            "discriminators": [{"text": "mk1 and mk4", "ids": ["p_1", "p_4"]}], "unresolved": [], "would_change": ["mk4 negative"]}


def test_render_roundtrip_fixture():
    case, _ = importers.load(FIX)
    text = ledger_io.render_case(case)
    back, _ = importers.parse_markdown(text)
    key = lambda f: (f.id, f.source, f.section, f.field, f.value, f.candidate)  # noqa: E731
    assert [key(f) for f in back.facts] == [key(f) for f in case.facts]
    assert back.candidates == case.candidates
    assert text.startswith("Candidate answers: K1; K2;")
    lean, _ = importers.parse_markdown(ledger_io.render_case(case, evidence=False))
    assert len(lean.facts) == 111 and all(f.evidence == "" for f in lean.facts if f.source != "who")


def test_render_has_no_leak():
    case, _ = importers.load(FIX)
    case.meta["variant"] = "dec-mk1"
    case.meta["perturbation_id"] = "SYN-003/dec-mk1"
    case.meta["rationale"] = "flipping mk1 makes K8 the best fit"
    text = ledger_io.render_case(case)
    for forbidden in ("SYN-003", "ground truth", "dec-mk1", "best fit", "truth"):
        assert forbidden not in text


def test_case_and_trace_json_roundtrip(tmp_path):
    case, trace = importers.load(FIX)
    d = ledger_io.case_to_dict(case)
    assert ledger_io.case_to_dict(ledger_io.case_from_dict(d)) == d
    t = ledger_io.trace_to_dict(trace)
    assert ledger_io.trace_to_dict(ledger_io.trace_from_dict(t)) == t
    ledger_io.write_cases(tmp_path / "c.jsonl", [case])
    assert ledger_io.load_cases(tmp_path / "c.jsonl")[0].case_id == "SYN-003"
    assert ledger_io.fact_fingerprint(case) == ledger_io.fact_fingerprint(ledger_io.case_from_dict(d))
    case.facts[0].value = "Negative"
    assert ledger_io.fact_fingerprint(case) != ledger_io.fact_fingerprint(ledger_io.case_from_dict(d))


def test_parse_output_contract():
    case, _ = importers.load(FIX)
    good = _good(case)
    t, w = ledger_io.parse_output("Here is my answer:\n```json\n" + json.dumps(good) + "\n```\nThanks.", case)
    assert w == [] and t.report.contract_valid is True and t.meta["parse_mode"] == "contract"
    assert t.report.decision == "K1" and t.report.sections[0].segments[0].citation_ids == ["p_1", "p_4"]
    assert t.rationale is not None and len(t.rationale.differential) == 8 and t.rationale.discriminators[0]["ids"] == ["p_1", "p_4"]
    assert t.rationale.differential[0].criteria[0].status == "met"
    assert t.meta["decision_status"] == "definitive" and t.meta["confidence"] == "high"
    t2, w2 = ledger_io.parse_output(json.dumps(good).replace('"would_change": ["mk4 negative"]}', '"would_change": ["mk4 negative"],}'), case)
    assert w2 == ["JSON_REPAIRED"] and t2.report.contract_valid is True


def test_parse_output_enable_shape_and_inline_ids():
    case, _ = importers.load(FIX)
    t, w = ledger_io.parse_output(json.dumps({"predicted_diagnosis": "K1", "sections": [{"title": "S", "segments": [{"text": "mk1 positive", "citation_ids": ["p_1"]}]}]}), case)
    assert t.report.decision == "K1" and t.report.contract_valid and "NO_RATIONALE" in w
    t, w = ledger_io.parse_output(json.dumps({"decision": "K1", "report": {"sections": [{"title": "S", "segments": ["mk1 positive [p_1]"]}]}}), case)
    assert t.report.sections[0].segments[0].citation_ids == ["p_1"] and "CITATIONS_INLINE" in w


def test_parse_output_fallbacks():
    case, _ = importers.load(FIX)
    t, w = ledger_io.parse_output("Decision: K1\nConfidence: high\nBecause p_1 and p_4.", case)
    assert "NO_JSON" in w and t.meta["parse_mode"] == "text_fallback" and t.report.contract_valid is False
    assert t.report.decision == "K1" and t.report.sections[0].segments[0].citation_ids == ["p_1", "p_4"]
    t, w = ledger_io.parse_output("The findings fit category K1 (K1) best.", case)
    assert t.report.decision == "K1"
    t, w = ledger_io.parse_output("I conclude as above.", case, thinking="blah\n" + json.dumps(_good(case)))
    assert "JSON_IN_REASONING" in w and t.report.contract_valid is True
    t, w = ledger_io.parse_output(json.dumps({"decision": "K1", "report": {"sections": [{"title": "S", "segments": [{"text": "x", "citation_ids": ["p_999"]}]}]}}), case)
    assert "UNKNOWN_IDS" in w and t.report.contract_valid is False and t.meta["unknown_ids"] == ["p_999"]
    t, w = ledger_io.parse_output(json.dumps({"decision": "Zeta", "report": {"sections": [{"title": "S", "segments": [{"text": "x", "citation_ids": ["p_1"]}]}]}}), case)
    assert "DECISION_NOT_CANDIDATE" in w and t.report.failure_kind == "DECISION_NOT_CANDIDATE"
    t, w = ledger_io.parse_output("", case)
    assert "MISSING_DECISION" in w and t.report.sections == []


def test_normalise_decision_and_hedge_signals():
    case, trace = importers.load(FIX)
    assert ledger_io.normalise_decision("K1", case) == ("K1", ["K1"], False)
    assert ledger_io.normalise_decision("indeterminate between K2 and K5", case) == ("K2", ["K2", "K5"], True)
    assert ledger_io.normalise_decision("Zeta", case) == ("OTHER", [], False)
    assert ledger_io.normalise_decision("", case) == ("UNRESOLVED", [], True)
    assert ledger_io.normalise_decision("indeterminate", case) == ("UNRESOLVED", [], True)
    pa, sig = ledger_io.ledger_answer(trace, case)
    assert pa.entity == "K1" and pa.hedged is False and sig["favoured"] == 1
    good = _good(case)
    good["decision_status"] = "provisional"
    t, _ = ledger_io.parse_output(json.dumps(good), case)
    pa, sig = ledger_io.ledger_answer(t, case)
    assert pa.hedged and sig["status"] and not sig["confidence_low"]
    good["decision_status"] = "definitive"
    good["confidence"] = "low"
    pa, sig = ledger_io.ledger_answer(ledger_io.parse_output(json.dumps(good), case)[0], case)
    assert pa.hedged and sig["confidence_low"]
    good["confidence"] = "high"
    good["differential"][1]["verdict"] = "favoured"
    pa, sig = ledger_io.ledger_answer(ledger_io.parse_output(json.dumps(good), case)[0], case)
    assert pa.hedged and sig["favoured_count"] and sig["favoured"] == 2


def test_render_minimal_case_without_reference_or_evidence():
    case = LedgerCase("x", "A", ["A", "B"], [Fact("p_1", "patient", "signals", "cpu_high", "Present", "cpu at 97%"),
                                             Fact("c_1", "context", "ticket", "priority", "High", "")])
    back, _ = importers.parse_markdown(ledger_io.render_case(case))
    assert [(f.id, f.source, f.section, f.field, f.value) for f in back.facts] == [("p_1", "patient", "signals", "cpu_high", "Present"),
                                                                                  ("c_1", "context", "ticket_context", "priority", "High")]
    assert back.candidates == ["A", "B"]
