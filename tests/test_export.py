import json

from traceaudit import export, segment


def test_bundle_structure(demo_run):
    out = demo_run / "export"
    index = json.loads((out / "index.json").read_text())
    assert index["bundle_version"] == 1 and index["cases"] and index["summary"] and index["study"]["rating_set"]
    assert {"dimensions", "error_tags"} <= set(index["rubric"])
    first = index["cases"][0]
    case = json.loads((out / first["file"]).read_text())
    assert set(case) == {"case", "variants", "traces", "base_reference"}
    assert "base" in case["variants"]
    tr = case["traces"][0]
    for k in ("trace_key", "reasoning", "answer", "claims", "grounding", "map"):
        assert k in tr
    for cl in tr["claims"]:
        assert tr["reasoning"][cl["start"]:cl["end"]] == cl["text"]
    dec = [v for v in case["variants"].values() if v["kind"] == "decisive"]
    if dec:
        assert dec[0]["diff"] and dec[0]["perturbation"]["primary_finding"]
    assert (out / "ratings-schema.json").exists() and (out / "figures").is_dir()
    assert (out / "index.json").stat().st_size < export.INDEX_LIMIT


def test_report_diff():
    d = export.report_diff("CD5+, CD23+.", "CD5+, CD23-.")
    assert len(d) == 1 and d[0]["before"] == "+" and d[0]["after"] == "-"


def test_build_map(lx):
    reasoning = "CD5 positive and CD23 positive. MCL is typically CD23 negative. So this favours CLL. Therefore CLL/SLL."
    claims = segment.segment(reasoning, "k", lx)
    for c in claims:
        if c.type == "factual":
            c.label = "supported"
    m = export.build_map(claims, "CLL_SLL", lx)
    kinds = {e["kind"] for e in m["edges"]}
    assert "conclusion" in kinds and m["nodes"][-1]["type"] == "answer"
    assert any(n["type"] == "knowledge" for n in m["nodes"]) and m["heuristic"]
    assert not m["nodes"][-1]["break"]


def test_ratings_import_and_validation(tmp_path):
    good = {"schema_version": 1, "study_id": "s", "rater_id": "R01", "trace_key": "a|base|low|0", "dimension": "D1", "score": 3,
            "submitted_at": "2026-01-01T00:00:00Z", "blinded": True}
    later = {**good, "score": 4, "submitted_at": "2026-01-02T00:00:00Z"}
    bad = {**good, "dimension": "D9"}
    unblinded = {**good, "dimension": "D2", "blinded": False}
    tags = {**good, "dimension": "tags", "score": None, "error_tags": ["none"]}
    src = tmp_path / "r.jsonl"
    src.write_text("\n".join(json.dumps(x) for x in (good, later, bad, unblinded, tags)) + "\n")
    n, probs = export.import_ratings(src, tmp_path / "ratings")
    assert n == 2 and len(probs) == 2
    stored = [json.loads(l) for l in open(tmp_path / "ratings" / "s" / "R01.jsonl")]
    assert {r["dimension"]: r.get("score") for r in stored} == {"D1": 4, "tags": None}
    assert export.validate_rating(good) == []


def test_select_rating_set(demo_run):
    keys = export.select_rating_set(demo_run / "grounding.jsonl", 10, 1, {"CLL-001": "CLL_SLL"})
    assert len(keys) == 10 and len(set(keys)) == 10
    assert not any("neu-" in k or "auth-right" in k for k in keys)
