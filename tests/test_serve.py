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
                        anonymous="analyse", allow_clients={"sim"}, rate_per_min=1000)
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
    assert st == 200 and cs[0]["id"] == "sample" and cs[0]["approved"] and cs[0]["n_cases"] == 6


def test_analyse_extracted_oracle(server, by_case):
    base, _ = server
    c = by_case["CLL-001"]
    body = {"reports": c.reports, "reasoning": "CD5 positive and CD23 positive. CD103 positive. Therefore CLL/SLL.",
            "answer": "Integrated diagnosis: Chronic lymphocytic leukaemia"}
    st, out = call(base, "POST", "/api/analyse", body)
    assert st == 200 and out["oracle"] == "extracted"
    assert out["case"]["truth"] == c.truth
    labels = [cl["label"] for cl in out["claims"] if cl["type"] == "factual"]
    assert labels == ["supported", "unsupported"]
    assert out["grounding"]["answer_entity"] == "CLL_SLL" and out["map"]["nodes"][-1]["type"] == "answer"
    st, out2 = call(base, "POST", "/api/analyse", {**body, "truth": {"CD5": "neg"}})
    assert out2["oracle"] == "truth" and out2["claims"][0]["label"] == "contradicted"


def test_analyse_validation(server):
    base, _ = server
    st, out = call(base, "POST", "/api/analyse", {"reports": {}, "reasoning": "x", "answer": "y"})
    assert st == 400 and out["error"]["code"] == "bad_request"
    st, out = call(base, "POST", "/api/analyse", {"reports": {"clinical": "x" * 60000}, "reasoning": "", "answer": ""})
    assert st == 400 and out["error"]["code"] == "too_large"


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
                        operator_keys={"anthropic": "sk-site"}, max_calls_per_job=50, max_calls_per_day=60)
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
    assert [x["id"] for x in lst][:1] == ["default"] and any(x["id"] == meta["id"] for x in lst)
    ex = json.loads(Path(__file__).resolve().parents[1].joinpath("examples", "incident-trace.json").read_text())
    st, out = call(base, "POST", "/api/analyse", {**ex, "lexicon_id": meta["id"]})
    assert st == 200 and out["domain"] == "incident-triage"
    assert [s["id"] for s in out["case"]["sections"]] == ["alerts", "logs", "deploys"]
    assert out["grounding"]["answer_entity"] == "BAD_DEPLOY"
    assert [c["label"] for c in out["claims"] if c["type"] == "factual"] == ["supported", "contradicted", "supported"]
    st, out = call(base, "POST", "/api/lexicons", {"lexicon": "{\"version\": 1}"})
    assert st == 400 and out["error"]["code"] == "bad_lexicon"
    st, out = call(base, "POST", "/api/analyse", {**ex, "lexicon_id": "lex-nope"})
    assert st == 404
