"""The engine's trace page copied as plain text imports like its Markdown file."""
from pathlib import Path

from traceaudit import importers, ledger
from traceaudit.importers.copied_text import looks_copied, normalise

FIX_MD = Path(__file__).with_name("fixtures") / "enable_trace_case_003.md"
FIX_TXT = Path(__file__).with_name("fixtures") / "enable_trace_case_002_copied.txt"


def test_detects_copied_form_only():
    assert looks_copied(FIX_TXT.read_text(encoding="utf-8"))
    assert not looks_copied(FIX_MD.read_text(encoding="utf-8"))
    assert not looks_copied("## Clinical summary\nCD5 positive.\n")


def test_copied_trace_imports_completely():
    case, trace = importers.parse_markdown(FIX_TXT.read_text(encoding="utf-8"))
    assert case.case_id == "case_002" and case.truth == "CLL/SLL" and case.meta["model"] == "gpt-oss:20b"
    assert case.candidates == ["CLL/SLL", "FL", "HCL", "LPL/WM", "MCL", "SBLPN", "SDRPL", "SMZL"]
    by_source = {}
    for f in case.facts:
        by_source[f.source] = by_source.get(f.source, 0) + 1
    assert by_source == {"patient": 61, "context": 8, "who": 42}  # w_83..w_85 share one row and become three facts
    p1 = next(f for f in case.facts if f.id == "p_1")
    assert (p1.section, p1.field, p1.value, p1.evidence) == ("immunophenotyping", "CD5", "Positive", "positive for CD5")
    c = next(f for f in case.facts if f.id == "c_110")
    assert (c.source, c.field, c.value) == ("context", "splenomegaly", "Present")
    w = next(f for f in case.facts if f.id == "w_70")
    assert w.candidate == "FL" and w.field == "essential_diagnostic_criteria"
    assert trace.thinking.startswith("We need to produce integrated haematopathology report") and "characters." not in trace.thinking[:40]
    r = trace.report
    assert r.decision == "CLL/SLL" and r.delivered_decision == "CLL/SLL" and r.contract_valid is False and r.failure_kind == "citation_contract_warning"
    assert [(s.title, len(s.segments)) for s in r.sections][:2] == [("ICD codes:", 1), ("Summary of diagnosis:", 2)]
    assert r.dropped_segments == [{"section": "Summary of diagnosis", "text": "Additional comments: None"}]
    rat = trace.rationale
    assert rat.decision == "CLL/SLL" and rat.confidence == "high" and len(rat.key_findings) == 21
    assert [d.verdict for d in rat.differential] == ["favoured", "unlikely", "excluded", "unlikely", "unlikely", "excluded", "excluded", "excluded"]
    assert all(len(d.criteria) == 1 for d in rat.differential)
    assert rat.differential[1].criteria[0].ids == ["w_70", "p_10"] and rat.differential[1].criteria[0].status == "not_met"
    assert [d["ids"] for d in rat.discriminators] == [["p_10"], ["p_30"], ["p_55"]]
    assert len(rat.unresolved) == 2 and len(rat.would_change) == 3 and rat.thinking.startswith("We need to produce JSON with key_findings")
    assert trace.ablation.removed_ids == ["p_10", "p_30", "p_55"] and trace.ablation.changed is False
    res = ledger.audit(case, trace)
    assert res["metrics"]["checks_total"] == 24 and 0.6 < res["metrics"]["grounding_rate"] < 0.8
    assert {c["id"]: c["status"] for c in res["checks"]}["discriminators_load_bearing"] == "FAIL"


def test_normalise_is_stable():
    text = FIX_TXT.read_text(encoding="utf-8")
    once = normalise(text)
    assert not looks_copied(once)
    a = importers.parse_markdown(text)
    b = importers.parse_markdown(once)
    assert len(a[0].facts) == len(b[0].facts) and a[1].report.decision == b[1].report.decision


def test_cli_audit_reads_copied_text(tmp_path, capsys):
    from traceaudit.cli import main
    assert main(["ledger", "audit", str(FIX_TXT)]) in (0, 1)
    out = capsys.readouterr().out
    assert "checks" in out.lower() and "case_002" in out


def test_not_before_a_positive_cue_reads_as_negative():
    """`TP53 variant not detected` is a negative statement; the cue grammar used to swallow `not` as a modifier."""
    case, _ = importers.parse_markdown(FIX_TXT.read_text(encoding="utf-8"))
    lx = ledger.lexicon_from_case(case)
    grades = {t: ledger.grade_segment(ledger.Segment(t, ["p_53"]), case, lx)["cited"][0] for t in
              ("TP53 variant not detected", "TP53 variant detected", "TP53 is not strongly expressed", "No TP53 aberration detected by NGS")}
    assert (grades["TP53 variant not detected"]["grade"], grades["TP53 variant not detected"]["stated"]) == ("agree", "neg")
    assert grades["TP53 variant detected"]["grade"] == "disagree"
    assert grades["TP53 is not strongly expressed"]["stated"] == "neg"
    assert grades["No TP53 aberration detected by NGS"]["stated"] == "neg"
