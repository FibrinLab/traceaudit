import io
import json
import urllib.error
from pathlib import Path as _Path

import pytest

from traceaudit import experiment
from traceaudit.clients import make_client
from traceaudit.clients.anthropic_ import AnthropicClient, parse_message
from traceaudit.clients.base import ClientError, GenerateRequest, RawResponse
from traceaudit.clients.callable_ import CallableClient
from traceaudit.simulate import SimParams


def test_plan_is_deterministic_and_interleaved(sample_cases, sample_perts, lx):
    a = experiment.plan(sample_cases, sample_perts, ("low", "high"), 2, 1, lexicon=lx)
    b = experiment.plan(sample_cases, sample_perts, ("low", "high"), 2, 1, lexicon=lx)
    assert [j.trace_key for j in a] == [j.trace_key for j in b]
    assert len({j.trace_key for j in a}) == len(a)
    efforts_first_20 = {j.effort for j in a[:20]}
    assert len(efforts_first_20) == 2
    assert any(j.variant == "base" for j in a) and any(j.variant.startswith("dec-") for j in a)
    c = experiment.plan(sample_cases, sample_perts, ("low",), 1, 2, lexicon=lx)
    assert [j.trace_key for j in c] != [j.trace_key for j in a if j.effort == "low" and j.run == 0]


def test_plan_filters_and_unreviewed(sample_cases, sample_perts, lx):
    jobs = experiment.plan(sample_cases, sample_perts, ("low",), 1, 0, case_filter=["CLL-001"], variant_filter=["base", "neu-*"], lexicon=lx)
    assert {j.case_id for j in jobs} == {"CLL-001"} and {j.variant for j in jobs} == {"base", "neu-1"}
    drafts = [c.copy() for c in sample_cases]
    for c in drafts:
        c.review.status = "draft"
    assert experiment.plan(drafts, sample_perts, ("low",), 1, 0, lexicon=lx) == []
    assert experiment.plan(drafts, sample_perts, ("low",), 1, 0, allow_unreviewed=True, lexicon=lx)


def test_per_trace_seed_stable():
    assert experiment.per_trace_seed(1, "a|base|low|0") == experiment.per_trace_seed(1, "a|base|low|0")
    assert experiment.per_trace_seed(1, "a|base|low|0") != experiment.per_trace_seed(2, "a|base|low|0")


def _run(tmp_path, client, jobs, **kw):
    lx = __import__("traceaudit.lexicon", fromlist=["load"]).load()
    prompt = experiment.load_prompt("enable-v3")
    man = experiment.build_manifest("x", client, prompt, ["low"], 1, 0, None, None, lx, 1, 0, {}, {}, 1)
    counts = experiment.run_experiment(jobs, client, tmp_path, man, prompt, 0, sleep=lambda s: None, **kw)
    return counts, [json.loads(l) for l in open(tmp_path / "traces.jsonl")], experiment.read_manifest(tmp_path)


def test_run_writes_traces_manifest_and_resumes(tmp_path, sample_cases, sample_perts, lx):
    client = make_client("sim", "simulated", params=SimParams(), seed=0)
    jobs = experiment.plan(sample_cases[:2], [], ("low",), 2, 0, lexicon=lx)
    counts, traces, man = _run(tmp_path, client, jobs)
    assert counts["ok"] == 4 and len(traces) == 4 and man["status"] == "complete" and man["n_errors"] == 0
    assert all(t["raw"] == "" and t["reasoning"] and t["answer"].startswith("Integrated diagnosis") for t in traces)
    counts2, traces2, _ = _run(tmp_path, client, jobs)
    assert counts2["ok"] == 0 and len(traces2) == 4
    counts3, traces3, _ = _run(tmp_path, client, jobs, force=True)
    assert counts3["ok"] == 4 and len(traces3) == 4


def test_no_trace_key_in_prompt(tmp_path, sample_cases, sample_perts, lx):
    """The prompt a model sees must not carry the trace key: its variant slug names the edited finding."""
    seen: list[GenerateRequest] = []

    def fn(system, user, effort, seed, **kw):
        seen.append((user, kw.get("meta")))
        return {"reasoning": "r", "answer": "Integrated diagnosis: CLL/SLL"}

    jobs = experiment.plan(sample_cases[:1], sample_perts, ("low",), 1, 0, lexicon=lx)
    assert any(j.variant.startswith("dec-") for j in jobs)
    _run(tmp_path, CallableClient(fn), jobs)
    assert seen and all("trace_key" not in user and "<!--" not in user for user, _ in seen)
    assert all(meta and meta["trace_key"] and meta["kind"] for _, meta in seen)
    keys = {meta["trace_key"] for _, meta in seen}
    assert keys == {j.trace_key for j in jobs}
    man = experiment.read_manifest(tmp_path)
    assert man["prompt"]["embed_trace_key"] is False


def test_request_meta_per_call(tmp_path, sample_cases, sample_perts, lx):
    """Variant metadata travels with each request, so parallel workers cannot see another job's metadata."""
    jobs = experiment.plan(sample_cases[:2], sample_perts, ("low", "high"), 2, 0, lexicon=lx)
    one = make_client("sim", "simulated", params=SimParams(), seed=0)
    four = make_client("sim", "simulated", params=SimParams(), seed=0)
    _, traces1, _ = _run(tmp_path / "w1", one, jobs)
    _, traces4, _ = _run(tmp_path / "w4", four, jobs, workers=4)
    by1 = {t["trace_key"]: (t["reasoning"], t["answer"]) for t in traces1}
    by4 = {t["trace_key"]: (t["reasoning"], t["answer"]) for t in traces4}
    assert by1 == by4 and len(by1) == len(jobs)
    assert not four.kw.get("meta")  # nothing is left behind on the client


def test_error_traces_and_redo(tmp_path, sample_cases, lx):
    calls = {"n": 0}

    def fn(system, user, effort, seed, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            raise ClientError("http", "boom", retryable=False)
        return {"reasoning": "r", "answer": "Integrated diagnosis: CLL"}
    client = CallableClient(fn, "flaky")
    jobs = experiment.plan(sample_cases[:1], [], ("low",), 2, 0, lexicon=lx)
    counts, traces, man = _run(tmp_path, client, jobs)
    assert counts["errors"] == 1 and man["n_errors"] == 1
    assert sum(1 for t in traces if t["meta"]["error"]) == 1
    counts2, traces2, man2 = _run(tmp_path, client, jobs, redo_errors=True)
    assert counts2["ok"] == 1 and man2["n_errors"] == 0 and len(traces2) == 2


def test_retry_then_success(tmp_path, sample_cases, lx):
    calls = {"n": 0}

    def fn(system, user, effort, seed, **kw):
        calls["n"] += 1
        if calls["n"] < 3:
            raise ClientError("timeout", "slow", retryable=True)
        return {"reasoning": "r", "answer": "x"}
    jobs = experiment.plan(sample_cases[:1], [], ("low",), 1, 0, lexicon=lx)
    counts, traces, _ = _run(tmp_path, CallableClient(fn, "slow"), jobs)
    assert counts["ok"] == 1 and "RETRIES:2" in traces[0]["meta"]["parse_warnings"]


def test_health_check_abort(tmp_path, sample_cases, lx):
    class Shifty(CallableClient):
        n = 0

        def describe(self):
            Shifty.n += 1
            return {"tag": "m", "digest": f"d{Shifty.n}", "server_version": "1", "server": "x"}
    client = Shifty(lambda *a, **k: {"reasoning": "r", "answer": "x"}, "shifty")
    jobs = experiment.plan(sample_cases[:1], [], ("low",), 1, 0, lexicon=lx)
    with pytest.raises(experiment.ModelChanged):
        _run(tmp_path, client, jobs)
    assert experiment.read_manifest(tmp_path)["status"].startswith("aborted")


def test_manifest_check_on_demo(demo_run, lx):
    problems = experiment.manifest_check(demo_run, lx)
    assert problems == [], problems


def test_callable_client_validation():
    c = CallableClient(lambda *a, **k: {"nope": 1}, "bad")
    with pytest.raises(ClientError):
        c.generate(GenerateRequest("s", "u", "low", 1))
    c2 = CallableClient(lambda *a, **k: RawResponse("r", "a"), "ok")
    assert c2.generate(GenerateRequest("s", "u", "low", 1)).answer == "a"


# ---- AnthropicClient against recorded responses (no network) --------------------------------

FIX = _Path(__file__).parent / "fixtures" / "anthropic"


class _Resp(io.BytesIO):
    def __init__(self, payload: dict, headers: dict | None = None):
        super().__init__(json.dumps(payload).encode())
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


def _fake_urlopen(monkeypatch, script):
    """script: list of (payload | HTTPError) consumed per call; records request bodies/headers."""
    calls = []

    def urlopen(req, timeout=None, **kw):
        calls.append({"url": req.full_url, "headers": dict(req.header_items()), "body": json.loads(req.data) if req.data else None, "timeout": timeout})
        item = script.pop(0)
        if isinstance(item, Exception):
            raise item
        return _Resp(item)
    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    return calls


def _http_error(code, payload, headers=None):
    import email.message
    h = email.message.Message()
    for k, v in (headers or {}).items():
        h[k] = v
    return urllib.error.HTTPError("https://api.anthropic.com/v1/messages", code, "err", h, io.BytesIO(json.dumps(payload).encode()))


def _fixture(name):
    return json.loads((FIX / f"{name}.json").read_text())


def test_anthropic_request_shape_and_parse(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    calls = _fake_urlopen(monkeypatch, [_fixture("model_entry"), _fixture("ok_medium")])
    c = AnthropicClient(model="claude-opus-5-5", sleep=lambda s: None)
    d = c.describe()
    assert d["server"] == "anthropic" and d["reasoning_kind"] == "summarized" and d["digest"].startswith("models-api:") and d["auth"] == "api_key"
    assert calls[0]["url"].endswith("/v1/models/claude-opus-5-5") and calls[0]["headers"]["X-api-key"] == "test-key"
    r = c.generate(GenerateRequest("SYS", "USER", "medium", seed=7, temperature=1.0, top_p=1.0, max_tokens=16000, timeout_s=300))
    body = calls[1]["body"]
    assert body["model"] == "claude-opus-5-5" and body["max_tokens"] == 16000 and body["system"] == "SYS"
    assert body["messages"] == [{"role": "user", "content": "USER"}]
    assert body["thinking"] == {"type": "adaptive", "display": "summarized"} and body["output_config"] == {"effort": "medium"}
    assert not {"temperature", "top_p", "top_k", "seed"} & set(body) and "budget_tokens" not in json.dumps(body)
    assert calls[1]["headers"]["Anthropic-version"] == "2023-06-01" and calls[1]["timeout"] == 300
    assert r.reasoning.startswith("This looks like classic CLL") and r.answer.startswith("Integrated diagnosis: Chronic lymphocytic")
    assert r.finish_reason == "end_turn" and r.usage["input_tokens"] == 891 and r.usage["output_tokens"] == 1335
    assert "SUMMARISED_THINKING" in r.parse_warnings and "NO_REASONING" not in r.parse_warnings and "NO_FINAL" not in r.parse_warnings


def test_anthropic_oauth_headers(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "tok")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "key-should-not-be-used")
    calls = _fake_urlopen(monkeypatch, [_fixture("ok_medium")])
    c = AnthropicClient(sleep=lambda s: None)
    c.generate(GenerateRequest("s", "u", "low", 1))
    h = calls[0]["headers"]
    assert h["Authorization"] == "Bearer tok" and h["Anthropic-beta"] == "oauth-2025-04-20" and "X-api-key" not in h
    assert c.auth_kind == "oauth"


def test_anthropic_refusal_max_tokens_and_omitted():
    with pytest.raises(ClientError) as ei:
        parse_message(_fixture("refusal"), "", 1)
    assert ei.value.kind == "refusal" and "general_harms" in ei.value.message and not ei.value.retryable
    r = parse_message(_fixture("max_tokens"), "", 1)
    assert r.finish_reason == "max_tokens" and r.answer == "" and "NO_FINAL" in r.parse_warnings and r.reasoning
    r2 = parse_message(_fixture("omitted_thinking"), "", 1, display="omitted")
    assert r2.reasoning == "" and "NO_REASONING" in r2.parse_warnings and "SUMMARISED_THINKING" not in r2.parse_warnings
    with pytest.raises(ClientError) as ei2:
        parse_message({"type": "error", "error": {"type": "overloaded_error", "message": "busy"}}, "", 1)
    assert ei2.value.retryable


def test_anthropic_retry_after_then_success(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    slept = []
    calls = _fake_urlopen(monkeypatch, [_http_error(429, {"type": "error", "error": {"type": "rate_limit_error", "message": "slow down"}}, {"retry-after": "3"}),
                                        _fixture("ok_medium")])
    c = AnthropicClient(sleep=slept.append)
    r = c.generate(GenerateRequest("s", "u", "high", 1))
    assert r.answer and slept == [3.0] and len(calls) == 2 and calls[1]["body"]["output_config"] == {"effort": "high"}
    # non-retryable 400 propagates with status and no sleep
    _fake_urlopen(monkeypatch, [_http_error(400, {"type": "error", "error": {"type": "invalid_request_error", "message": "bad"}})])
    with pytest.raises(ClientError) as ei:
        c.generate(GenerateRequest("s", "u", "high", 1))
    assert not ei.value.retryable and ei.value.status == 400 and slept == [3.0]


def test_anthropic_run_through_experiment(tmp_path, sample_cases, lx, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    jobs = experiment.plan(sample_cases[:1], [], ("medium",), 2, 0, lexicon=lx)
    # describe() is called by build_manifest and again by the initial health check, then one call per job
    script = [_fixture("model_entry"), _fixture("model_entry"), _fixture("ok_medium"), _fixture("refusal")]
    _fake_urlopen(monkeypatch, script)
    client = AnthropicClient(sleep=lambda s: None)
    counts, traces, man = _run(tmp_path, client, jobs)
    assert counts["ok"] == 1 and counts["errors"] == 1
    assert man["model"]["reasoning_kind"] == "summarized" and man["model"]["digest"].startswith("models-api:")
    err = [t for t in traces if t["meta"]["error"]][0]
    assert err["meta"]["error"].startswith("refusal: general_harms")
    ok = [t for t in traces if not t["meta"]["error"]][0]
    assert "SUMMARISED_THINKING" in ok["meta"]["parse_warnings"] and ok["meta"]["finish_reason"] == "end_turn" and ok["server"] == "anthropic"
