import json
from collections import Counter
from pathlib import Path

import pytest

from traceaudit import importers, ledger
from traceaudit.cli import main
from traceaudit.tools import ledger_labels as ll

FIX = Path(__file__).with_name("fixtures") / "synthetic_trace_SYN-003.md"
GRADES = ll.HUMAN_GRADES


@pytest.fixture(scope="module")
def audit_result():
    case, trace = importers.load(FIX)
    return ledger.audit(case, trace)


def test_items_from_audit_counts(audit_result):
    items = ll.items_from_audit(audit_result)
    report_cited = [c for s in audit_result["sections"] for g in s["segments"] for c in g["cited"]]
    assert sum(1 for c in report_cited if c["grade"] in GRADES) == 26
    assert sum(1 for c in report_cited if c["grade"] == "reference") == 2          # left out: mechanical
    assert sum(1 for i in items if i["source"] == "report") == 26
    assert sum(1 for i in items if i["source"] == "rationale") == 50 and len(items) == 76
    assert {i["grade"] for i in items} <= set(GRADES) and not any(i["fact_id"].startswith("w_") for i in items)
    assert len({i["item_id"] for i in items}) == len(items)
    for i in items:
        assert set(i) >= {"item_id", "case_id", "source", "section", "segment_text", "fact_id", "field", "value", "evidence", "grade", "kind"}
        assert i["case_id"] == "SYN-003" and len(i["item_id"]) == 16
    by_id = {i["item_id"]: i for i in items}
    nm = next(i for i in items if i["section"] == "rationale.differential.K1" and i["fact_id"] == "p_2")
    assert nm["grade"] == "not_mentioned" and nm["field"] == "mk2" and nm["evidence"].startswith("positive for mk1 mk2")
    assert ll.items_from_audit(audit_result)[0]["item_id"] in by_id  # stable ids across calls
    assert ll.item_id("SYN-003", "rationale.differential.K1", nm["segment_text"], "p_2") == nm["item_id"]
    assert sum(1 for i in items if i["kind"] == "uncited") == 0
    # the rationale's criteria rows are not items (they state what a candidate requires, not what the patient has)
    assert not any("criteria" in i["section"] for i in items)
    assert ll.items_from_audit({"case_id": "x", "sections": [], "facts": [], "rationale": None}) == []


def _synthetic_items(n_cases=6, per_case=12):
    items = []
    grades = ["agree"] * 6 + ["disagree", "disagree", "unverifiable", "unverifiable", "not_mentioned", "not_mentioned"]
    for c in range(n_cases):
        for k in range(per_case):
            src = "report" if k % 2 else "rationale"   # every grade in both sources: 8 strata
            items.append({"item_id": ll.item_id(f"c{c}", src, f"seg {k}", f"p_{k}"), "case_id": f"c{c}", "source": src, "section": src,
                          "segment_text": f"seg {k}", "fact_id": f"p_{k}", "field": "F", "value": "Positive", "evidence": "", "kind": "citation",
                          "stated": None, "grade": grades[k]})
    return items


def test_sample_stratified_and_deterministic():
    items = _synthetic_items()
    s1 = ll.sample(items, 24, seed=5)
    s2 = ll.sample(list(reversed(items)), 24, seed=5)
    assert s1 == s2 and len(s1) == 24
    assert [i["item_id"] for i in ll.sample(items, 24, seed=6)] != [i["item_id"] for i in s1]
    strata = Counter((i["grade"], i["source"]) for i in s1)
    assert len(strata) == 8 and max(strata.values()) == 3 and min(strata.values()) == 3   # 8 strata, round-robin
    assert max(Counter(i["case_id"] for i in s1).values()) <= max(5, -(-2 * 24 // 6))
    capped = ll.sample(items, 60, seed=5, per_case=4)
    assert len(capped) == 24 and max(Counter(i["case_id"] for i in capped).values()) == 4
    assert len(ll.sample(items, 1000, seed=1)) == len(items)
    assert ll.sample([], 10, seed=1) == []
    assert s1 == sorted(s1, key=lambda i: (i["case_id"], i["item_id"]))


def test_rater_files_are_blind_and_shuffled():
    sampled = ll.sample(_synthetic_items(), 30, seed=7)
    files = ll.rater_files(sampled, ["R01", "R02"], seed=7)
    assert set(files) == {"R01", "R02"}
    for rid, rows in files.items():
        assert len(rows) == 30 and all("grade" not in r and "stated" not in r for r in rows)
        assert all(r["human_grade"] == "" and r["note"] == "" and r["rater_id"] == rid for r in rows)
        assert {r["item_id"] for r in rows} == {i["item_id"] for i in sampled}
        assert list(rows[0])[:4] == ["item_id", "rater_id", "human_grade", "note"]
    assert [r["item_id"] for r in files["R01"]] != [r["item_id"] for r in files["R02"]]
    assert [r["item_id"] for r in files["R01"]] != [i["item_id"] for i in sampled]
    assert ll.rater_files(sampled, ["R01"], seed=7)["R01"] == files["R01"]           # same seed, same order


def test_agreement_report_shape_and_values():
    grader = []
    grades = ["agree"] * 8 + ["disagree"] * 4 + ["unverifiable"] * 4 + ["not_mentioned"] * 4
    for k, g in enumerate(grades):
        grader.append({"item_id": f"i{k:02}", "case_id": f"c{k % 6}", "source": "report", "grade": g})
    r1 = [{"item_id": g["item_id"], "human_grade": g["grade"]} for g in grader]
    flips = {"i00": "unverifiable", "i01": "unverifiable", "i08": "agree", "i16": "unverifiable"}
    r2 = [{"item_id": g["item_id"], "human_grade": flips.get(g["item_id"], g["grade"])} for g in grader]
    # po = 16/20; R01 marginals 8,4,4,4; R02 7,3,7,3 -> pe = (56 + 12 + 28 + 12) / 400 = 0.27; kappa = 0.53 / 0.73
    rep = ll.agreement({"R01": r1, "R02": r2}, grader, B=100, seed=1)
    assert rep["n_items"] == 20 and rep["n_cases"] == 6 and rep["raters"] == ["R01", "R02"]
    assert rep["n_unlabelled"] == 0 and rep["n_disagreements_between_raters"] == 4 and rep["n_consensus"] == 16 and rep["n_unresolved"] == 4
    pair = rep["inter_rater"]["pairwise"]["R01|R02"]
    assert pair["n"] == 20 and pair["cohen_kappa"]["point"] == pytest.approx(0.53 / 0.73, abs=5e-5)
    assert pair["cohen_kappa"]["ci_method"] == "bootstrap" and pair["cohen_kappa"]["lo"] <= pair["cohen_kappa"]["point"] <= pair["cohen_kappa"]["hi"]
    assert pair["percent_agreement"]["point"] == 0.8
    assert rep["inter_rater"]["gwet_ac1"]["point"] is not None and rep["inter_rater"]["mean_cohen_kappa"] == round(0.53 / 0.73, 4)
    gvc = rep["grader_vs_consensus"]
    assert gvc["n"] == 16 and gvc["cohen_kappa"]["point"] == 1.0 and gvc["confusion"]["agree"]["agree"] == 6
    assert gvc["per_class"]["disagree"]["precision"] == 1.0 and gvc["per_class"]["disagree"]["support"] == 3
    assert rep["grader_vs_rater"]["R01"]["cohen_kappa"] == 1.0 and rep["grader_vs_rater"]["R02"]["cohen_kappa"] == pytest.approx(0.53 / 0.73, abs=5e-5)
    acc = rep["acceptance"]
    assert acc["accepted"] is True and acc["threshold"] == round(0.53 / 0.73 - 0.1, 4) and acc["grader_kappa"] == 1.0
    assert rep["label_counts"]["grader"] == {"agree": 8, "disagree": 4, "not_mentioned": 4, "unverifiable": 4}
    assert rep["problems"] == [] and ll.summary_text(rep).startswith("20 items from 6 case(s)")
    # adjudication resolves disagreements; blanks and unknown grades are counted, not crashed on
    adj = [{"item_id": "i00", "human_grade": "agree"}, {"item_id": "i08", "human_grade": "unverifiable"}]
    r2b = [dict(r) for r in r2]
    r2b[5]["human_grade"] = ""
    r2b[6]["human_grade"] = "maybe"
    rep2 = ll.agreement({"R01": r1, "R02": r2b}, grader, adj, B=50, seed=1)
    assert rep2["consensus_source"] == {"unanimous": 14, "adjudicated": 2} and rep2["n_consensus"] == 16
    assert rep2["n_unlabelled"] == 2 and rep2["n_invalid"] == 1 and any("maybe" in p for p in rep2["problems"])
    assert rep2["inter_rater"]["pairwise"]["R01|R02"]["n"] == 18
    assert rep2["grader_vs_consensus"]["confusion"]["unverifiable"]["disagree"] == 1   # i08: grader disagree, adjudicated unverifiable
    # three raters: a strict majority stands in for adjudication
    r3 = [{"item_id": g["item_id"], "human_grade": g["grade"]} for g in grader]
    rep3 = ll.agreement({"R01": r1, "R02": r2, "R03": r3}, grader, B=20, seed=1)
    assert rep3["consensus_source"] == {"unanimous": 16, "majority": 4} and len(rep3["inter_rater"]["pairwise"]) == 3


def test_cli_sample_then_agreement_round_trip(tmp_path, capsys):
    out = tmp_path / "labels"
    assert main(["ledger", "sample", str(FIX), "--n", "20", "--raters", "R01,R02", "--seed", "20261029", "--out", str(out)]) == 0
    assert "sampled 20" in capsys.readouterr().out
    assert sorted(p.name for p in out.iterdir()) == ["R01.jsonl", "R02.jsonl", "grader.jsonl", "manifest.json"]
    grader = [json.loads(l) for l in (out / "grader.jsonl").read_text().splitlines()]
    assert len(grader) == 20 and all("grade" in g for g in grader)
    assert json.loads((out / "manifest.json").read_text())["n_items_available"] == 76
    # the raters fill in their files: R01 copies the grader, R02 differs on three items
    by_id = {g["item_id"]: g["grade"] for g in grader}
    for rid, flips in (("R01", 0), ("R02", 3)):
        rows = [json.loads(l) for l in (out / f"{rid}.jsonl").read_text().splitlines()]
        assert all(r["human_grade"] == "" and "grade" not in r for r in rows)
        for k, r in enumerate(rows):
            r["human_grade"] = "disagree" if k < flips and by_id[r["item_id"]] != "disagree" else by_id[r["item_id"]]
        (out / f"{rid}.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    assert main(["ledger", "agreement", str(out), "--B", "50"]) == 0
    captured = capsys.readouterr()
    rep = json.loads(captured.out)
    assert rep["n_items"] == 20 and rep["n_disagreements_between_raters"] == 3 and rep["n_consensus"] == 17
    assert rep["grader_vs_consensus"]["cohen_kappa"]["point"] == 1.0 and rep["acceptance"]["accepted"] is True
    assert "grader vs consensus" in captured.err
    # an adjudicated file settles the three
    adj = [{"item_id": r["item_id"], "human_grade": by_id[r["item_id"]]} for r in
           [json.loads(l) for l in (out / "R02.jsonl").read_text().splitlines()][:3]]
    (out / "adjudicated.jsonl").write_text("".join(json.dumps(r) + "\n" for r in adj))
    assert main(["ledger", "agreement", str(out), "--adjudicated", str(out / "adjudicated.jsonl"), "--B", "50"]) == 0
    rep = json.loads(capsys.readouterr().out)
    assert rep["n_consensus"] == 20 and rep["consensus_source"]["adjudicated"] == 3
    # the audit command keeps its syntax
    assert main(["ledger", "audit", str(FIX), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["case_id"] == "SYN-003"
