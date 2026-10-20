from traceaudit import extract, grounding, segment
from traceaudit.schema import Trace


def _trace(reasoning, answer="Integrated diagnosis: Chronic lymphocytic leukaemia"):
    return Trace("CLL-001|base|medium|0", "CLL-001", "base", "medium", 0, "m", reasoning, answer)


def _ground(lx, case, reasoning, answer="Integrated diagnosis: Chronic lymphocytic leukaemia", verifier=None):
    t = _trace(reasoning, answer)
    claims = segment.segment(reasoning, t.trace_key, lx)
    rec = grounding.ground(t, case.truth, claims, extract.finding_spans(case, lx), case.entity, verifier, lx)
    return rec, claims


def test_supported(lx, by_case):
    c = by_case["CLL-001"]
    rec, claims = _ground(lx, c, "CD5 positive and CD23 positive. Therefore CLL.")
    assert rec.n_supported == 1 and rec.grounding_rate == 1.0
    assert claims[0].label == "supported"
    assert claims[0].evidence[0].report == "flow_cytometry"


def test_contradicted_precedence(lx, by_case):
    c = by_case["CLL-001"]
    rec, claims = _ground(lx, c, "CD5 negative, CD23 positive and CD999 positive.")
    assert claims[0].label == "contradicted"
    assert rec.contradicted_findings == ["CD5"]


def test_unsupported_not_tested(lx, by_case):
    c = by_case["CLL-001"]
    absent = next(f for f in ("CD103", "CD123", "annexin_A1") if f not in c.truth)
    alias = lx.aliases(absent)[0]
    rec, claims = _ground(lx, c, f"{alias} positive.")
    assert claims[0].label == "unsupported" and rec.unsupported_findings == [absent]
    assert claims[0].evidence[0].span is None


def test_ambiguous_excluded(lx, by_case):
    c = by_case["CLL-001"]
    rec, claims = _ground(lx, c, "CD5 positive and CD5 negative.")
    assert claims[0].label == "ambiguous" and rec.n_ambiguous == 1 and rec.grounding_rate is None


def test_conditional_and_knowledge_not_graded(lx, by_case):
    c = by_case["CLL-001"]
    rec, claims = _ground(lx, c, "If CD5 were negative this would be odd. MCL is typically CD23 negative.")
    assert rec.n_factual == 0 and rec.n_inferential == 1 and rec.n_knowledge == 1


def test_variant_relative_oracle(lx, by_case, sample_perts):
    from traceaudit import perturb
    c = by_case["CLL-001"]
    p = next(p for p in sample_perts if p.case_id == "CLL-001" and p.variant == "dec-cyclin_d1")
    v = perturb.apply(c, p, lx, verify=False)
    t = _trace("Cyclin D1 negative, so CLL.")
    claims = segment.segment(t.reasoning, t.trace_key, lx)
    rec = grounding.ground(t, v.truth, claims, extract.finding_spans(v, lx), "MCL", None, lx)
    assert claims[0].label == "contradicted"
    assert rec.answer_correct is False


def test_answer_fields_and_trace_agreement(lx, by_case):
    c = by_case["CLL-001"]
    rec, _ = _ground(lx, c, "CD5 positive. Overall the diagnosis is CLL.", "Integrated diagnosis: Mantle cell lymphoma")
    assert rec.answer_entity == "MCL" and rec.answer_correct is False
    assert rec.trace_conclusion_entity == "CLL_SLL" and rec.trace_answer_agree is False


def test_lexical_verifier(lx, by_case):
    c = by_case["CLL-001"]
    rec, claims = _ground(lx, c, "MCL is typically CD23 negative. MCL is usually CD5 negative. FL is commonly CD38 positive.",
                          verifier=grounding.LexicalVerifier())
    verdicts = [cl.knowledge_check.verdict for cl in claims]
    assert verdicts == ["consistent", "inconsistent", "abstain"]
    assert (rec.knowledge_consistent, rec.knowledge_inconsistent, rec.knowledge_abstain) == (1, 1, 1)


def test_has_inference_sensitivity_counts(lx, by_case):
    c = by_case["CLL-001"]
    rec, _ = _ground(lx, c, "CD5 positive, consistent with CLL. CD23 positive.")
    assert rec.n_has_inference == 1 and rec.n_graded_no_inference == 1 and rec.n_supported_no_inference == 1


def test_error_trace_skipped(lx, by_case):
    t = _trace("")
    t.meta.error = "timeout"
    rec = grounding.ground(t, by_case["CLL-001"].truth, [], {}, "CLL_SLL", None, lx)
    assert rec.error == "timeout" and rec.n_claims == 0
