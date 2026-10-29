"""The viewer's example artefact (a software incident, no reference-domain data) imports and grades as intended."""
from pathlib import Path

from traceaudit import ledger
from traceaudit.importers import parse_markdown

EXAMPLE = Path(__file__).resolve().parents[1] / "viewer" / "public" / "examples" / "incident-trace-artefact.md"


def test_example_artefact_grades_as_designed():
    case, trace = parse_markdown(EXAMPLE.read_text(encoding="utf-8"))
    assert case.case_id == "INC-001" and case.truth == "faulty deployment" and len(case.facts) == 12
    res = ledger.audit(case, trace)
    m = res["metrics"]
    # one planted error: the report and the thinking say CPU was elevated; the alert recorded CPU normal
    assert (m["cited_agree"], m["cited_disagree"], m["cited_unverifiable"]) == (8, 1, 0)
    failed = {c["id"] for c in res["checks"] if c["status"] == "FAIL"}
    assert failed == {"citations_agree", "thinking_agrees"}
    assert res["decision"] == "faulty deployment"


def test_field_aliases_cover_hyphen_and_space_forms():
    assert "on-call note" in ledger.field_aliases("on_call_note") and "on call note" in ledger.field_aliases("on_call_note")
    assert "error rate" in ledger.field_aliases("error_rate")
