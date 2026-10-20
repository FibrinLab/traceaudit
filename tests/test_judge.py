import json

import pytest

from traceaudit import judge
from traceaudit.clients.callable_ import CallableClient
from traceaudit.schema import Trace


def test_parse_judge_output():
    s, t, r, c = judge.parse_judge_output('Sure: {"scores":{"D1":3,"D2":4,"D3":2,"D4":3,"D5":4,"D6":2,"D7":3},"error_tags":["ignored_finding","bogus","none"],"rationale":{"D1":"ok"},"overall_comment":"fine"} trailing')
    assert s["D2"] == 4 and t == ["ignored_finding"] and r == {"D1": "ok"} and c == "fine"
    with pytest.raises(ValueError):
        judge.parse_judge_output('{"scores":{"D1":5}}')
    with pytest.raises(ValueError):
        judge.parse_judge_output("no json here")


def test_judge_trace_retry_and_blinding():
    seen = []

    def fn(system, user, effort, seed, **kw):
        seen.append(user)
        if len(seen) == 1:
            return {"reasoning": "", "answer": "not json"}
        return {"reasoning": "", "answer": json.dumps({"scores": {d: 3 for d in judge.DIM_IDS}, "error_tags": [], "rationale": {}, "overall_comment": ""})}
    t = Trace("C-1|dec-x|low|0", "C-1", "dec-x", "low", 0, "m", "REASONING", "ANSWER")
    rec = judge.judge_trace(CallableClient(fn, "j"), t, "RENDER", "jm")
    assert rec.error is None and rec.meta["attempts"] == 2 and rec.scores["D1"] == 3
    assert "RENDER" in seen[0] and "REASONING" in seen[0] and "ANSWER" in seen[0]
    for forbidden in ("dec-x", "truth", "supported", "contradicted", "low"):
        assert forbidden not in seen[0].replace("REASONING", "").replace("ANSWER", "").replace("RENDER", "")


def test_judge_unparseable_twice_records_error():
    fn = lambda *a, **k: {"reasoning": "", "answer": "nope"}  # noqa: E731
    t = Trace("C-1|base|low|0", "C-1", "base", "low", 0, "m", "r", "a")
    rec = judge.judge_trace(CallableClient(fn, "j"), t, "x", "jm")
    assert rec.error and rec.error.startswith("unparseable")


def test_prompt_file_matches_code():
    from pathlib import Path
    p = json.loads((Path(judge.__file__).with_name("prompts") / "judge-v1.json").read_text())
    assert p["sha256"] == judge.prompt_sha256()
    assert "D7" in p["system"] and "unacknowledged_cue" in p["system"]
