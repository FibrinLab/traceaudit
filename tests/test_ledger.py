import json
from pathlib import Path

from traceaudit import importers, ledger

FIX = Path(__file__).with_name("fixtures") / "enable_trace_case_003.md"


def test_import_enable_markdown():
    case, trace = importers.load(FIX)
    assert case.case_id == "case_003" and case.truth == "CLL/SLL"
    assert case.candidates == ["CLL/SLL", "FL", "HCL", "LPL/WM", "MCL", "SBLPN", "SDRPL", "SMZL"]
    by = case.by_id()
    assert by["p_1"].field == "CD5" and by["p_1"].value == "Positive" and by["p_1"].polarity == "pos"
    assert by["c_111"].source == "context" and by["c_111"].value == "Present"
    assert by["w_65"].source == "who" and by["w_65"].candidate == "CLL/SLL"
    assert by["w_84"].candidate == "MCL"  # split "w_83, w_84, w_85"
    assert sum(1 for f in case.facts if f.source == "patient") == 61 and sum(1 for f in case.facts if f.source == "context") == 8
    assert trace.thinking.startswith("We need to produce")
    assert trace.report.decision == "CLL/SLL" and trace.report.delivered_decision == "CLL/SLL" and trace.report.contract_valid is False
    assert [s.title for s in trace.report.sections][:2] == ["ICD codes:", "Summary of diagnosis:"]
    assert trace.report.dropped_segments == [{"section": "Summary of diagnosis", "text": "Diagnosis: CLL/SLL"}]
    assert trace.rationale.decision == "CLL/SLL" and trace.rationale.confidence == "high"
    assert len(trace.rationale.differential) == 8 and trace.rationale.differential[0].verdict == "favoured"
    assert trace.rationale.differential[0].criteria[0].ids == ["w_62", "p_1"]
    assert trace.rationale.discriminators[0]["ids"] == ["p_1", "p_4", "p_23"]
    assert trace.ablation.removed_ids == ["p_1", "p_4", "p_23", "p_55", "p_57"] and trace.ablation.changed is False


def test_value_polarity():
    assert ledger.value_polarity("Positive") == "pos" and ledger.value_polarity("Weak") == "pos"
    assert ledger.value_polarity("Absent") == "neg" and ledger.value_polarity("Not performed") == "untested"
    assert ledger.value_polarity("132") == "other" and ledger.value_polarity("Not mentioned") == "untested"


def test_audit_on_enable_sample():
    case, trace = importers.load(FIX)
    res = ledger.audit(case, trace)
    status = {c["id"]: c["status"] for c in res["checks"]}
    assert status["citations_exist"] == "PASS"
    assert status["citations_agree"] == "PASS"
    assert status["decision_matches_truth"] == "PASS"
    assert status["thinking_considers_alternatives"] == "FAIL"
    assert status["discriminators_load_bearing"] == "FAIL"
    assert status["coverage"] == "FAIL" and res["metrics"]["ignored"] == 39  # the original engine counted 38; the fixture trims one thinking sentence (t(14;18) not performed)
    assert status["coverage_informative"] == "FAIL"
    assert status["differential_complete"] == "PASS" and status["one_favoured"] == "PASS"
    assert status["criteria_cited"] == "FAIL"       # only the definition (w_62) was cited, not w_65
    assert status["contradicting_evidence_informative"] == "FAIL"  # HCL/SDRPL contradicted with p_25 'Not mentioned'
    assert status["nothing_dropped"] == "FAIL" and status["report_contract"] == "FAIL"
    assert status["summary_structure"] == "FAIL"    # Diagnosis line was dropped
    imm = next(s for s in res["sections"] if s["title"].startswith("Immunophenotyping"))
    grades = {c["id"]: c["grade"] for c in imm["segments"][0]["cited"]}
    assert grades["p_1"] == "agree" and grades["p_10"] == "agree" and grades["p_7"] == "agree"
    morph = next(s for s in res["sections"] if s["title"].startswith("Morphology"))
    g = {c["id"]: c["grade"] for c in morph["segments"][0]["cited"]}
    assert g["p_22"] == "agree"  # "no prominent nucleoli" vs prominent_nucleoli Negative
    assert res["metrics"]["checks_failed"] >= 6 and res["metrics"]["cited_disagree"] == 0
    json.dumps(res)  # serialisable


def test_disagreement_is_caught():
    case, trace = importers.load(FIX)
    seg = trace.report.sections[2].segments[0]
    seg.text = seg.text.replace("CD10 negative", "CD10 positive")
    res = ledger.audit(case, trace)
    status = {c["id"]: c["status"] for c in res["checks"]}
    assert status["citations_agree"] == "FAIL" and res["metrics"]["cited_disagree"] == 1
    trace.thinking += " Also CD23 negative here."
    res = ledger.audit(case, trace)
    assert {c["id"]: c["status"] for c in res["checks"]}["thinking_agrees"] == "FAIL"


def test_review_rows_and_audit_many():
    case, trace = importers.load(FIX)
    res = ledger.audit(case, trace)
    rows = ledger.review_rows(res)
    # one row per citation occurrence (a fact cited twice gives two rows), plus one per uncited assertion
    assert len(rows) == sum(len(seg["cited"]) + len(seg["uncited_assertions"]) for s in res["sections"] for seg in s["segments"])
    assert len({r["fact_id"] for r in rows if r["kind"] == "cited"}) == res["metrics"]["cited_in_report"]
    assert {r["kind"] for r in rows} <= {"cited", "uncited"}
    assert all(set(r) == set(ledger.REVIEW_COLUMNS) - {"human_grade", "note"} for r in rows)
    cited = [r for r in rows if r["kind"] == "cited"]
    assert sum(1 for r in cited if r["grade"] == "agree") == res["metrics"]["cited_agree"]
    agg = ledger.audit_many([res, res])
    assert agg["n"] == 2 and [pc["case_id"] for pc in agg["per_case"]] == ["case_003", "case_003"]
    assert agg["check_pass_rates"]["citations_agree"] == {"title": "Cited facts are stated with their recorded value", "pass": 2, "fail": 0, "n": 2, "pass_rate": 1.0}
    assert agg["check_pass_rates"]["thinking_considers_alternatives"]["pass_rate"] == 0.0
    assert agg["grade_counts"]["cited"]["agree"] == 2 * res["metrics"]["cited_agree"]
    assert agg["decision_matches_truth"] == {"n": 2, "matches": 2}


def test_ledger_audit_cli_many(tmp_path, capsys):
    import csv
    from traceaudit.cli import main
    d = tmp_path / "artefacts"
    d.mkdir()
    (d / "a.md").write_text(FIX.read_text(encoding="utf-8"), encoding="utf-8")
    (d / "sub").mkdir()
    (d / "sub" / "b.md").write_text(FIX.read_text(encoding="utf-8"), encoding="utf-8")
    sheet = tmp_path / "review.csv"
    rc = main(["ledger", "audit", str(d), "--review-sheet", str(sheet)])
    out = capsys.readouterr().out
    assert rc == 1 and "2 artefact(s)" in out and "check pass rates:" in out and "citation grades:" in out
    rows = list(csv.DictReader(open(sheet, encoding="utf-8")))
    assert rows and list(rows[0]) == ledger.REVIEW_COLUMNS and all(r["human_grade"] == "" for r in rows)
    assert len(rows) == 2 * len(ledger.review_rows(ledger.audit(*importers.load(FIX))))
    assert main(["ledger", "audit", str(FIX), "--json"]) == 0
    single = json.loads(capsys.readouterr().out)
    assert single["case_id"] == "case_003" and "per_case" not in single
    assert main(["ledger", "audit", str(FIX), "--summary", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["n"] == 1
