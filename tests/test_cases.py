import json
from pathlib import Path

from traceaudit import cases as cases_mod, lexicon
from traceaudit.cli import main

ROOT = Path(__file__).resolve().parents[1]


def test_build_case_from_documents_incident_domain(tmp_path):
    lx = lexicon.load(ROOT / "examples" / "lexicon-incident-triage.json")
    ex = json.loads((ROOT / "examples" / "incident-trace.json").read_text())
    case, probs = cases_mod.build_case({"case_id": "INC-001", "entity": "BAD_DEPLOY", "documents": ex["documents"]}, lx)
    assert probs == [] and case.truth["recent_deploy"] == "pos" and case.truth["error_rate_elevated"] == "pos"
    assert [s["id"] for s in case.sections] == ["alerts", "logs", "deploys"]
    bad, probs = cases_mod.build_case({"case_id": "INC-002", "entity": "NOPE", "documents": ex["documents"], "truth": {"disk_full": "pos"}}, lx)
    assert any("not in the lexicon" in p for p in probs) and any("truth says disk_full=pos" in p for p in probs)


def test_cases_build_cli(tmp_path):
    ex = json.loads((ROOT / "examples" / "incident-trace.json").read_text())
    src = tmp_path / "docs.jsonl"
    src.write_text(json.dumps({"case_id": "INC-001", "entity": "BAD_DEPLOY", "documents": ex["documents"]}) + "\n")
    out = tmp_path / "cases.jsonl"
    rc = main(["--lexicon", str(ROOT / "examples" / "lexicon-incident-triage.json"), "cases", "build", str(src), "-o", str(out), "--approve"])
    assert rc == 0
    rec = json.loads(out.read_text())
    assert rec["review"]["status"] == "approved" and rec["sections"][0]["id"] == "alerts" and rec["truth"]["recent_deploy"] == "pos"
