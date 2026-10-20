import json
import subprocess
import sys
from pathlib import Path

from traceaudit.cli import main


def test_demo_is_deterministic(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    assert main(["demo", "--out", str(a), "--runs", "2", "--B", "50"]) == 0
    assert main(["demo", "--out", str(b), "--runs", "2", "--B", "50"]) == 0
    for name in ("claims.jsonl", "grounding.jsonl", "counterfactual.jsonl", "authority.jsonl"):
        assert (a / name).read_text() == (b / name).read_text(), name
    sa, sb = json.loads((a / "summary.json").read_text()), json.loads((b / "summary.json").read_text())
    for k in ("run_id", "generated"):
        sa.pop(k), sb.pop(k)
    assert sa == sb


def test_validate_and_report(demo_run, capsys):
    pkg = Path(__file__).resolve().parents[1] / "traceaudit" / "domains" / "haematology"
    assert main(["validate", str(pkg / "sample_cases.jsonl"), "--perturbations", str(pkg / "sample_perturbations.jsonl")]) == 0
    assert main(["report", str(demo_run)]) == 0
    out = capsys.readouterr().out
    assert "RQ1 Grounding" in out and "silent_rate" in out
    assert main(["manifest", "check", str(demo_run)]) == 0


def test_perturb_and_casegen_commands(tmp_path):
    cases = tmp_path / "cases.jsonl"
    assert main(["casegen", "-o", str(cases), "--per-entity", "1", "--approve-all"]) == 0
    perts = tmp_path / "perts.jsonl"
    assert main(["perturb", str(cases), "-o", str(perts), "--approve-all"]) == 0
    assert main(["validate", str(cases), "--perturbations", str(perts)]) == 0
    sheet = tmp_path / "review.csv"
    assert main(["review-sheet", str(cases), "-o", str(sheet)]) == 0
    assert "case_id" in sheet.read_text()


def test_entrypoint_runs():
    r = subprocess.run([sys.executable, "-m", "traceaudit.cli", "--version"], capture_output=True, text=True)
    assert r.returncode == 0 and "traceaudit" in r.stdout
