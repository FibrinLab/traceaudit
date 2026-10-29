import json
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from traceaudit import serve
from traceaudit.serve import ServiceConfig, make_server

PKG = Path(__file__).resolve().parents[1] / "traceaudit"


@pytest.fixture()
def server(tmp_path):
    cfg = ServiceConfig(root=tmp_path / "root", host="127.0.0.1", port=0, tokens={"tok-a": "wsA", "tok-b": "wsB"},
                        anonymous="analyse", allow_clients={"sim"}, rate_per_min=1000, domain="haematology")
    httpd = make_server(cfg)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    yield base, httpd
    httpd.shutdown()
    httpd.server_close()


def call(base, method, path, body=None, token=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + path, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw and r.headers.get("Content-Type", "").startswith("application/json") else raw)
    except urllib.error.HTTPError as e:
        raw = e.read()
        return e.code, json.loads(raw) if raw else None


def test_health_lexicon_and_case_sets(server):
    base, _ = server
    st, h = call(base, "GET", "/api/health")
    assert st == 200 and h["workspace"] == "public" and "sim" in h["clients"]
    st, lx = call(base, "GET", "/api/lexicon")
    assert st == 200 and any(e["id"] == "MCL" for e in lx["entities"]) and len(lx["findings"]) > 50
    st, cs = call(base, "GET", "/api/case-sets", token="tok-a")
    assert st == 200 and cs[0]["id"] == "sample" and cs[0]["approved"] and cs[0]["n_cases"] == 6 and cs[0]["domain"] == "haematology"


def test_analyse_extracted_oracle(server, by_case):
    base, _ = server
    c = by_case["CLL-001"]
    body = {"reports": c.reports, "reasoning": "CD5 positive and CD23 positive. CD103 positive. Therefore CLL/SLL.",
            "answer": "Integrated diagnosis: Chronic lymphocytic leukaemia"}
    st, out = call(base, "POST", "/api/analyse", body)
    assert st == 200 and out["oracle"] == "extracted"
    # the text path now returns a ledger result: facts from the documents, factual claims as cited segments
    assert {f["field"]: f["value"].lower()[:3] for f in out["facts"]} == {k: v for k, v in c.truth.items()}
    assert out["decision"] == "CLL_SLL" and out["truth"] is None and "CLL_SLL" in out["candidates"]
    assert "claims" not in out and "grounding" not in out and "map" not in out and "parsed_answer" not in out
    segs = out["sections"][0]["segments"]
    assert [[x["grade"] for x in s["cited"]] for s in segs] == [["agree", "agree"], []]
    assert segs[1]["uncited_assertions"][0]["grade"] == "unknown_fact"  # CD103 is stated in no document: unsupported in the old labels
    assert out["metrics"]["grounding_rate"] == 1.0 and out["metrics"]["uncited_assertions"] == 1
    status = {ch["id"]: ch["status"] for ch in out["checks"]}
    assert status["citations_agree"] == "PASS" and status["segments_cited"] == "FAIL"
    assert [d["id"] for d in out["documents"]] == ["clinical", "morphology", "flow_cytometry", "cytogenetics", "molecular"]
    evidence = {f["id"]: f["evidence"] for f in out["facts"]}
    for d in out["documents"]:
        for sp in d["facts"]:
            assert d["text"][sp["start"]:sp["end"]] == evidence[sp["id"]]
    assert out["answer"]["entity"] == "CLL_SLL" and out["answer"]["hedged"] is False and out["answer"]["claims"] == 3
    st, out2 = call(base, "POST", "/api/analyse", {**body, "truth": {"CD5": "neg"}})
    assert out2["oracle"] == "truth" and out2["sections"][0]["segments"][0]["cited"][0]["grade"] == "disagree"
    assert out2["metrics"]["cited_disagree"] == 1 and out2["metrics"]["grounding_rate"] == 0.5


def test_analyse_validation(server):
    base, _ = server
    st, out = call(base, "POST", "/api/analyse", {"reports": {}, "reasoning": "x", "answer": "y"})
    assert st == 400 and out["error"]["code"] == "bad_request"
    st, out = call(base, "POST", "/api/analyse", {"reports": {"clinical": "x" * 60000}, "reasoning": "", "answer": ""})
    assert st == 400 and out["error"]["code"] == "too_large"
    st, out = call(base, "POST", "/api/analyse", {"reports": {"clinical": "CD5 positive."}, "reasoning": ["not", "text"], "answer": ""})
    assert st == 400 and out["error"]["code"] == "bad_request"
    # an empty reasoning is still a ledger result: no segments, the checks that need thinking fail
    st, out = call(base, "POST", "/api/analyse", {"reports": {"clinical": "CD5 positive."}, "reasoning": "", "answer": ""})
    assert st == 200 and out["sections"][0]["segments"] == [] and out["metrics"]["grounding_rate"] is None
    assert {c["id"]: c["status"] for c in out["checks"]}["thinking_present"] == "FAIL" and out["decision"] == "UNRESOLVED"


def test_auth_gating(server):
    base, _ = server
    st, out = call(base, "POST", "/api/jobs", {"client": {"kind": "sim"}, "case_set": "sample"})
    assert st == 401 and out["error"]["code"] == "auth_required"
    st, out = call(base, "GET", "/api/case-sets", token="nope")
    assert st == 401 and out["error"]["code"] == "bad_token"
    st, out = call(base, "POST", "/api/jobs", {"client": {"kind": "openai", "model": "x"}, "case_set": "sample"}, token="tok-a")
    assert st == 403 and out["error"]["code"] == "client_not_allowed"


def test_sim_job_end_to_end(server):
    base, httpd = server
    st, out = call(base, "POST", "/api/jobs", {"client": {"kind": "sim", "api_key": "secret"}, "case_set": "sample",
                                               "efforts": ["low"], "runs": 1, "variants": ["base", "dec-*", "neu-*", "auth-wrong-*"], "sim_p": 0.2},
                   token="tok-a")
    assert st == 202
    job_id = out["job_id"]
    deadline = time.time() + 120
    while time.time() < deadline:
        st, j = call(base, "GET", f"/api/jobs/{job_id}", token="tok-a")
        if j["status"] in serve.TERMINAL:
            break
        time.sleep(0.5)
    assert j["status"] == "done", j
    assert j["progress"]["done"] == j["progress"]["total"] > 0 and j["headline"]["grounding_rate"] is not None
    assert "api_key" not in json.dumps(j)
    job_json = json.loads((httpd.service.root / "jobs" / job_id / "job.json").read_text())
    assert "secret" not in json.dumps(job_json)
    st, idx = call(base, "GET", f"/api/jobs/{job_id}/bundle/index.json", token="tok-a")
    assert st == 200 and idx["cases"] and idx["summary"]
    first = idx["cases"][0]["file"]
    st, cf = call(base, "GET", f"/api/jobs/{job_id}/bundle/{first}", token="tok-a")
    assert st == 200 and cf["traces"]
    st, rep = call(base, "GET", f"/api/jobs/{job_id}/files/report.md", token="tok-a")
    assert st == 200 and b"RQ1 Grounding" in rep
    st, out = call(base, "GET", f"/api/jobs/{job_id}", token="tok-b")
    assert st == 404
    st, lst = call(base, "GET", "/api/jobs", token="tok-a")
    assert [x["job_id"] for x in lst] == [job_id]


def test_cancel_and_unapproved_and_upload(server, sample_cases):
    base, _ = server
    st, up = call(base, "POST", "/api/uploads", {"name": "mine", "cases": "\n".join(c.to_json() for c in sample_cases[:2]), "approved": False}, token="tok-a")
    assert st == 201 and up["n_cases"] == 2 and up["n_perturbations"] > 0
    st, out = call(base, "POST", "/api/jobs", {"client": {"kind": "sim"}, "case_set": up["upload_id"]}, token="tok-a")
    assert st == 409 and out["error"]["code"] == "case_set_unapproved"
    st, out = call(base, "GET", "/api/case-sets", token="tok-b")
    assert all(c["id"] != up["upload_id"] for c in out)
    bad = sample_cases[0].to_dict()
    bad["truth"]["CD5"] = "neg" if bad["truth"]["CD5"] == "pos" else "pos"
    st, out = call(base, "POST", "/api/uploads", {"cases": json.dumps(bad)}, token="tok-a")
    assert st == 400 and out["error"]["code"] == "invalid_cases"
    st, up2 = call(base, "POST", "/api/uploads", {"name": "ok", "cases": "\n".join(c.to_json() for c in sample_cases[:1]), "approved": True}, token="tok-a")
    st, out = call(base, "POST", "/api/jobs", {"client": {"kind": "sim"}, "case_set": up2["upload_id"], "efforts": ["low"], "runs": 1}, token="tok-a")
    assert st == 202
    st, out = call(base, "DELETE", f"/api/jobs/{out['job_id']}", token="tok-a")
    assert st in (200, 409)


def test_static_fallback(tmp_path):
    static = tmp_path / "dist"
    static.mkdir()
    (static / "index.html").write_text("<html>viewer</html>")
    cfg = ServiceConfig(root=tmp_path / "root", port=0, static=static)
    httpd = make_server(cfg)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        st, body = call(base, "GET", "/")
        assert st == 200 and b"viewer" in body
        st, body = call(base, "GET", "/some/route")
        assert st == 200 and b"viewer" in body
        st, out = call(base, "GET", "/api/nope")
        assert st == 404
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_operator_key_and_caps(tmp_path):
    cfg = ServiceConfig(root=tmp_path / "root", port=0, tokens={"t": "ws"}, anonymous="all", allow_clients={"sim", "anthropic"},
                        operator_keys={"anthropic": "sk-site"}, max_calls_per_job=50, max_calls_per_day=60, domain="haematology")
    httpd = make_server(cfg)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        st, h = call(base, "GET", "/api/health")
        assert h["operator_keys"] == ["anthropic"] and h["limits"]["max_calls_per_job"] == 50
        # too large for one job: sample = 36 jobs x 3 efforts x 1 run = 108 > 50
        st, out = call(base, "POST", "/api/jobs", {"client": {"kind": "anthropic", "model": "claude-opus-5-5"}, "case_set": "sample", "runs": 1})
        assert st == 400 and out["error"]["code"] == "job_too_large"
        # no key for a kind without an operator key
        st, out = call(base, "POST", "/api/jobs", {"client": {"kind": "openai", "model": "x"}, "case_set": "sample"})
        assert st == 403
        httpd.service.cfg.allow_clients.add("openai")
        st, out = call(base, "POST", "/api/jobs", {"client": {"kind": "openai", "model": "x"}, "case_set": "sample", "efforts": ["low"], "runs": 1})
        assert st == 403 and out["error"]["code"] == "key_required"
        # within the per-job cap on the site key: 36 calls; the job will fail at the network, but it is accepted and counted
        st, out = call(base, "POST", "/api/jobs", {"client": {"kind": "anthropic", "model": "claude-opus-5-5", "endpoint": "http://127.0.0.1:9"},
                                                   "case_set": "sample", "efforts": ["low"], "runs": 1})
        assert st == 202
        st, j = call(base, "GET", f"/api/jobs/{out['job_id']}")
        assert j["config"]["key_source"] == "operator" and 30 <= j["config"]["estimated_calls"] <= 36 and "sk-site" not in json.dumps(j)
        # daily budget: another 36 would exceed 60
        st, out2 = call(base, "POST", "/api/jobs", {"client": {"kind": "anthropic", "model": "claude-opus-5-5"}, "case_set": "sample", "efforts": ["low"], "runs": 1})
        assert st == 429 and out2["error"]["code"] == "budget_exhausted"
        httpd.service.jobs[out["job_id"]].stop.set()
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_custom_lexicon_and_documents(server):
    base, _ = server
    lex_text = Path(__file__).resolve().parents[1].joinpath("examples", "lexicon-incident-triage.json").read_text()
    st, meta = call(base, "POST", "/api/lexicons", {"lexicon": lex_text, "name": "incident"})
    assert st == 201 and meta["domain"] == "incident-triage" and [s["id"] for s in meta["sections"]] == ["alerts", "logs", "deploys"]
    st, lst = call(base, "GET", "/api/lexicons")
    assert [x["id"] for x in lst][:1] == ["default"] and any(x["id"] == meta["id"] for x in lst) and any(x["id"] == "example:incident-triage" for x in lst)
    ex = json.loads(Path(__file__).resolve().parents[1].joinpath("examples", "incident-trace.json").read_text())
    st, out = call(base, "POST", "/api/analyse", {**ex, "lexicon_id": meta["id"]})
    assert st == 200 and out["domain"] == "incident-triage" and out["lexicon"]["id"] == meta["id"]
    assert [(d["id"], d["title"]) for d in out["documents"]] == [("alerts", "Alerts"), ("logs", "Logs"), ("deploys", "Deploy history")]
    assert out["decision"] == "BAD_DEPLOY" and out["candidates"] == ["BAD_DEPLOY", "CAPACITY", "DATABASE", "DISK"]
    # the old labels supported, contradicted, supported become citation grades
    assert [[x["grade"] for x in s["cited"]] for s in out["sections"][0]["segments"]] == [["agree", "agree"], ["disagree"], ["agree"]]
    assert out["metrics"]["grounding_rate"] == 0.75 and out["metrics"]["facts"] == 7
    st, out = call(base, "POST", "/api/lexicons", {"lexicon": "{\"version\": 1}"})
    assert st == 400 and out["error"]["code"] == "bad_lexicon"
    st, out = call(base, "POST", "/api/analyse", {**ex, "lexicon_id": "lex-nope"})
    assert st == 404


def test_bare_server_has_no_built_in_domain(tmp_path, sample_cases):
    cfg = ServiceConfig(root=tmp_path / "root", port=0, tokens={"t": "ws"}, anonymous="all", allow_clients={"sim"})
    httpd = make_server(cfg)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        st, h = call(base, "GET", "/api/health")
        assert h["domain"] is None and h["sections"] == [] and h["lexicon_version"] is None
        st, lst = call(base, "GET", "/api/lexicons")
        assert [x["source"] for x in lst] == ["example"] and lst[0]["id"] == "example:incident-triage"
        st, cs = call(base, "GET", "/api/case-sets")
        assert cs == []
        ex = json.loads(Path(__file__).resolve().parents[1].joinpath("examples", "incident-trace.json").read_text())
        st, out = call(base, "POST", "/api/analyse", ex)
        assert st == 400 and out["error"]["code"] == "lexicon_required"
        st, out = call(base, "POST", "/api/analyse", {**ex, "lexicon_id": "example:incident-triage"})
        assert st == 200 and out["domain"] == "incident-triage" and out["decision"] == "BAD_DEPLOY" and out["metrics"]["cited_disagree"] == 1
        # uploading cases needs a lexicon too; with the example it works and the sim audit runs on it
        st, out = call(base, "POST", "/api/uploads", {"name": "h", "cases": "\n".join(c.to_json() for c in sample_cases[:1]), "approved": True})
        assert st == 400 and out["error"]["code"] == "lexicon_required"
        from traceaudit import cases as cases_mod, lexicon
        lx = lexicon.load(Path(__file__).resolve().parents[1] / "examples" / "lexicon-incident-triage.json")
        case, probs = cases_mod.build_case({"case_id": "INC-001", "entity": "BAD_DEPLOY", "documents": ex["documents"]}, lx, approve=True)
        st, up = call(base, "POST", "/api/uploads", {"name": "incidents", "cases": case.to_json(), "approved": True, "lexicon_id": "example:incident-triage"})
        assert st == 201 and up["domain"] == "incident-triage" and up["n_perturbations"] >= 2
        st, out = call(base, "POST", "/api/jobs", {"client": {"kind": "sim"}, "case_set": up["upload_id"], "efforts": ["low"], "runs": 1})
        assert st == 202
        deadline = time.time() + 120
        while time.time() < deadline:
            st, j = call(base, "GET", f"/api/jobs/{out['job_id']}")
            if j["status"] in serve.TERMINAL:
                break
            time.sleep(0.5)
        assert j["status"] == "done", j
        st, idx = call(base, "GET", f"/api/jobs/{out['job_id']}/bundle/index.json")
        assert st == 200 and idx["lexicon"]["version"] == "0.1.0"
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_ledger_endpoint(server):
    base, _ = server
    md = Path(__file__).with_name("fixtures").joinpath("synthetic_trace_SYN-003.md").read_text()
    st, out = call(base, "POST", "/api/ledger", {"markdown": md})
    assert st == 200 and out["case_id"] == "SYN-003" and out["metrics"]["facts"] == 111
    status = {c["id"]: c["status"] for c in out["checks"]}
    assert status["citations_exist"] == "PASS" and status["coverage"] == "FAIL"
    # round-trip through the JSON form
    st2, out2 = call(base, "POST", "/api/ledger", {"case": {"case_id": out["case_id"], "truth": out["truth"], "candidates": out["candidates"],
                                                            "facts": [{k: f[k] for k in ("id", "source", "section", "field", "value", "evidence", "candidate")} for f in out["facts"]]},
                                                   "trace": {"thinking": out["thinking"]["text"],
                                                             "report": {"decision": out["decision"], "sections": [{"title": s["title"], "segments": [{"text": g["text"], "citation_ids": g["citation_ids"]} for g in s["segments"]]} for s in out["sections"]]},
                                                             "rationale": out["rationale"], "ablation": out["ablation"]}})
    assert st2 == 200 and out2["metrics"]["cited_in_report"] == out["metrics"]["cited_in_report"]
    st, out = call(base, "POST", "/api/ledger", {"markdown": "nothing here"})
    assert st == 400
