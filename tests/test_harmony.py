
from traceaudit.clients import parse_harmony
from traceaudit.clients.base import ClientError, split_reasoning


def test_channels():
    raw = ("<|start|>assistant<|channel|>analysis<|message|>think 1<|end|>"
           "<|start|>assistant<|channel|>commentary to=functions.x<|constrain|>json<|message|>{}<|call|>"
           "<|start|>assistant<|channel|>analysis<|message|>think 2<|end|>"
           "<|start|>assistant<|channel|>final<|message|>Integrated diagnosis: MCL<|return|>")
    r, a, w = parse_harmony(raw)
    assert r.startswith("think 1\n\nthink 2") and "[commentary]" in r
    assert a == "Integrated diagnosis: MCL"
    assert set(w) == {"MULTI_ANALYSIS", "COMMENTARY_PRESENT"}


def test_no_final_and_truncation():
    r, a, w = parse_harmony("<|channel|>analysis<|message|>only thinking, cut off")
    assert r == "only thinking, cut off" and a == "" and "NO_FINAL" in w


def test_stray_and_no_channels():
    assert "STRAY_TEXT" in parse_harmony("hello <|channel|>final<|message|>x<|return|>")[2]
    r, a, w = parse_harmony("plain text answer")
    assert a == "plain text answer" and "NO_CHANNELS" in w


def test_verbatim_whitespace_preserved():
    r, a, _ = parse_harmony("<|channel|>analysis<|message|>  spaced \n\n<|end|><|channel|>final<|message|>\nans\n<|return|>")
    assert r == "  spaced \n\n" and a == "\nans\n"


def test_split_reasoning_structured_and_harmony_in_content():
    w = []
    assert split_reasoning("answer", "thinking", w) == ("thinking", "answer") and w == []
    r, a = split_reasoning("<|channel|>analysis<|message|>t<|end|><|channel|>final<|message|>f<|return|>", None, w)
    assert (r, a) == ("t", "f")
    r, a = split_reasoning("<|channel|>final<|message|>f<|return|>", "think", w)
    assert r == "think" and a == "f" and "HARMONY_IN_CONTENT" in w


def test_client_error_retryable():
    e = ClientError("timeout", "x", True)
    assert e.retryable and "timeout" in str(e)
