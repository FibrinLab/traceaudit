"""The engine's trace page copied as plain text imports like its Markdown file."""
from pathlib import Path

from synthetic_artefact import artefact_text, copied_text

from traceaudit import importers, ledger
from traceaudit.importers.copied_text import looks_copied, normalise

FIX_MD = Path(__file__).with_name("fixtures") / "synthetic_trace_SYN-003.md"


def test_detects_copied_form_only():
    assert looks_copied(copied_text())
    assert not looks_copied(FIX_MD.read_text(encoding="utf-8"))
    assert not looks_copied("## Clinical summary\nm1 positive.\n")


def test_copied_trace_imports_like_the_markdown():
    md = artefact_text()
    a_case, a_trace = importers.parse_markdown(md)
    b_case, b_trace = importers.parse_markdown(copied_text(md))
    key = lambda f: (f.id, f.source, f.section, f.field, f.value, f.evidence, f.candidate)  # noqa: E731
    assert [key(f) for f in b_case.facts] == [key(f) for f in a_case.facts] and b_case.candidates == a_case.candidates
    assert b_case.case_id == "SYN-003" and b_case.truth == "K1" and b_case.meta["model"] == "synthetic-engine"
    assert b_trace.thinking.strip() == a_trace.thinking.strip()
    assert (b_trace.report.decision, b_trace.report.delivered_decision, b_trace.report.contract_valid, b_trace.report.failure_kind) == ("K1", "K1", False, "citation_contract_warning")
    assert [(s.title, [(g.text, g.citation_ids) for g in s.segments]) for s in b_trace.report.sections] == \
        [(s.title, [(g.text, g.citation_ids) for g in s.segments]) for s in a_trace.report.sections]
    assert b_trace.report.dropped_segments == a_trace.report.dropped_segments
    ra, rb = a_trace.rationale, b_trace.rationale
    assert (rb.decision, rb.confidence, len(rb.key_findings)) == (ra.decision, ra.confidence, 21)
    assert [(d.diagnosis, d.verdict, d.supporting, d.contradicting, [(c.criterion, c.status, c.ids) for c in d.criteria]) for d in rb.differential] == \
        [(d.diagnosis, d.verdict, d.supporting, d.contradicting, [(c.criterion, c.status, c.ids) for c in d.criteria]) for d in ra.differential]
    assert rb.discriminators == ra.discriminators and rb.unresolved == ra.unresolved and rb.would_change == ra.would_change
    assert rb.thinking.strip() == ra.thinking.strip()
    assert b_trace.ablation == a_trace.ablation
    ma, mb = ledger.audit(a_case, a_trace)["metrics"], ledger.audit(b_case, b_trace)["metrics"]
    assert {k: v for k, v in mb.items() if k != "thinking_chars"} == {k: v for k, v in ma.items() if k != "thinking_chars"}


def test_normalise_is_stable():
    text = copied_text()
    once = normalise(text)
    assert not looks_copied(once)
    a = importers.parse_markdown(text)
    b = importers.parse_markdown(once)
    assert len(a[0].facts) == len(b[0].facts) and a[1].report.decision == b[1].report.decision


def test_cli_audit_reads_copied_text(tmp_path, capsys):
    from traceaudit.cli import main
    p = tmp_path / "pasted.txt"
    p.write_text(copied_text(), encoding="utf-8")
    assert main(["ledger", "audit", str(p)]) in (0, 1)
    out = capsys.readouterr().out
    assert "checks" in out.lower() and "SYN-003" in out


def test_not_before_a_positive_cue_reads_as_negative():
    """`GENE28 variant not detected` is a negative statement; the cue grammar used to swallow `not` as a modifier."""
    case, _ = importers.parse_markdown(artefact_text())
    lx = ledger.lexicon_from_case(case)
    grades = {t: ledger.grade_segment(ledger.Segment(t, ["p_53"]), case, lx)["cited"][0] for t in
              ("GENE28 variant not detected", "GENE28 variant detected", "GENE28 is not strongly expressed", "No GENE28 aberration detected by sequencing")}
    assert (grades["GENE28 variant not detected"]["grade"], grades["GENE28 variant not detected"]["stated"]) == ("agree", "neg")
    assert grades["GENE28 variant detected"]["grade"] == "disagree"
    assert grades["GENE28 is not strongly expressed"]["stated"] == "neg"
    assert grades["No GENE28 aberration detected by sequencing"]["stated"] == "neg"
