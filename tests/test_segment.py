from traceaudit import segment

TRACE = """We have a 72-year-old with lymphocytosis. Flow: CD5+, CD23+, CD200+ → classic CLL phenotype.
MCL is typically CD23 negative and cyclin D1 positive. Is cyclin D1 positive here? Need to check whether t(11;14) was tested.
FISH shows no t(11;14). If cyclin D1 were positive this would be MCL.

- CD200 bright supports CLL over MCL.
- Therefore the diagnosis is CLL/SLL.
Hmm."""


def test_segment_types_in_order(lx):
    claims = segment.segment(TRACE, "k", lx)
    types = [(c.text[:20], c.type, tuple(c.flags)) for c in claims]
    assert types[0][1] == "factual"
    assert types[1] == ("Flow: CD5+, CD23+, C", "factual", ())
    assert types[3][1] == "knowledge"
    assert types[4] == ("Is cyclin D1 positiv", "other", ("question",))
    assert types[5][1] == "other"
    assert types[6] == ("FISH shows no t(11;1", "factual", ())
    assert types[7] == ("If cyclin D1 were po", "inferential", ("conditional",))
    assert types[8] == ("CD200 bright support", "factual", ("has_inference",))
    assert types[9][1] == "inferential"
    assert claims[8].paragraph_id == 1 and claims[0].paragraph_id == 0


def test_offsets_and_arrows(lx):
    claims = segment.segment(TRACE, "k", lx)
    for c in claims:
        assert TRACE[c.start:c.end] == c.text
    assert not any("→" in c.text for c in claims)


def test_abbreviation_guard(lx):
    claims = segment.segment("CD5 is positive, e.g. in CLL cases. Dr. Smith agreed with CD23 positivity.", "k", lx)
    assert len(claims) == 2


def test_trace_conclusion(lx):
    claims = segment.segment(TRACE, "k", lx)
    assert segment.trace_conclusion(claims, TRACE, lx) == "CLL_SLL"


def test_empty_and_short(lx):
    assert segment.segment("", "k", lx) == []
    assert segment.segment("OK. Hm", "k", lx) == []
