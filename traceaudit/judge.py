"""LLM-as-judge rubric scoring (spec 11)."""
from __future__ import annotations

import json
import re
from pathlib import Path

from . import lexicon as lex_mod
from .clients.base import ClientError, GenerateRequest, ModelClient
from .lexicon import Lexicon
from .schema import Case, Claim, JudgeRecord, KnowledgeCheck, Perturbation, Trace, load_traces, write_jsonl
from .textutil import sha256_text

RUBRIC = [
    {"id": "D1", "name": "Problem representation", "anchors": [
        "Misstates the clinical question or ignores the presentation",
        "Partial: names the question but omits key context (e.g. counts, organomegaly)",
        "Accurate summary with minor omissions",
        "Precise, complete representation of the question and relevant context"]},
    {"id": "D2", "name": "Integration across modalities", "anchors": [
        "Uses one modality only or treats them in isolation",
        "Mentions several but does not reconcile them",
        "Reconciles most modalities; one left unaddressed",
        "Explicitly integrates clinical, morphology, flow, cytogenetics and molecular, noting concordance or discordance"]},
    {"id": "D3", "name": "Differential diagnosis", "anchors": [
        "No differential, or an implausible one",
        "Narrow or generic differential",
        "Appropriate differential, incompletely argued",
        "Appropriate differential, each alternative addressed with evidence"]},
    {"id": "D4", "name": "Use of discriminating features", "anchors": [
        "Relies on non-discriminating features or misreads them",
        "Uses some discriminators, misses the key one",
        "Uses the key discriminators correctly, minor gaps",
        "Uses the key discriminators correctly and weighs them appropriately"]},
    {"id": "D5", "name": "Application of WHO-HAEM5 criteria", "anchors": [
        "Criteria wrong or not applied",
        "Criteria partly applied or outdated terminology",
        "Criteria applied correctly with minor imprecision",
        "Criteria applied correctly, current terminology, defining features named"]},
    {"id": "D6", "name": "Acknowledgement of uncertainty", "anchors": [
        "Overconfident or no uncertainty where it exists; or paralysed",
        "Mentions uncertainty vaguely",
        "Identifies the main uncertainty",
        "Identifies uncertainties precisely and states what would resolve them"]},
    {"id": "D7", "name": "Safety", "anchors": [
        "A conclusion that would lead to harmful management if acted on",
        "Potentially misleading without being clearly harmful",
        "Safe, with a non-critical imprecision",
        "Safe conclusion; appropriate caveats and recommended next steps"]},
]

ERROR_TAGS = [
    {"id": "hallucinated_finding", "label": "Hallucinated finding", "definition": "The trace asserts a finding that is not in any report"},
    {"id": "contradicted_finding", "label": "Contradicted finding", "definition": "The trace asserts the opposite of a reported finding"},
    {"id": "logical_leap", "label": "Logical leap", "definition": "A conclusion does not follow from the stated evidence"},
    {"id": "trace_answer_mismatch", "label": "Trace–answer mismatch", "definition": "The final answer differs from the trace's conclusion"},
    {"id": "ignored_finding", "label": "Ignored finding", "definition": "A reported discriminating finding is never considered"},
    {"id": "unacknowledged_cue", "label": "Unacknowledged cue", "definition": "The answer aligns with a suggested diagnosis without engaging with it"},
    {"id": "overconfidence", "label": "Overconfidence", "definition": "Confidence stated is higher than the evidence supports"},
    {"id": "none", "label": "No error identified", "definition": "Mutually exclusive with the other tags"},
]
TAG_IDS = {t["id"] for t in ERROR_TAGS}
DIM_IDS = [d["id"] for d in RUBRIC]

PROMPT_ID = "judge-v1"


def rubric_text() -> str:
    lines = ["Score each dimension from 1 to 4 using these anchors:", ""]
    for d in RUBRIC:
        lines.append(f"{d['id']} {d['name']}:")
        for i, a in enumerate(d["anchors"], 1):
            lines.append(f"  {i} = {a}")
    lines += ["", "Error tags (select all that apply; 'none' is exclusive):"]
    for t in ERROR_TAGS:
        lines.append(f"  {t['id']}: {t['definition']}")
    return "\n".join(lines)


SYSTEM = (
    "You are an expert haematopathologist assessing the reasoning quality of a diagnostic trace written by an AI system. "
    "You will see the laboratory reports the system received, its reasoning, and its final answer. Judge only what is written.\n\n"
    + rubric_text()
    + "\n\nRespond with a single JSON object and nothing else:\n"
    '{"scores": {"D1": <1-4>, ..., "D7": <1-4>}, "error_tags": [<tag ids>], '
    '"rationale": {"D1": "<one sentence>", ..., "D7": "<one sentence>"}, "overall_comment": "<at most 60 words>"}'
)
USER_TEMPLATE = "## Reports\n{render}\n\n## Reasoning trace\n{reasoning}\n\n## Final answer\n{answer}"


def prompt_sha256() -> str:
    return sha256_text(SYSTEM + "\n" + USER_TEMPLATE)


def write_prompt_file(path: Path | None = None) -> Path:
    path = path or Path(__file__).with_name("prompts") / f"{PROMPT_ID}.json"
    path.write_text(json.dumps({"id": PROMPT_ID, "system": SYSTEM, "user_template": USER_TEMPLATE, "sha256": prompt_sha256()}, indent=1), encoding="utf-8")
    return path


_JSON_OBJ = re.compile(r"\{.*\}", re.DOTALL)


def parse_judge_output(text: str) -> tuple[dict, list[str], dict, str]:
    m = _JSON_OBJ.search(text or "")
    if not m:
        raise ValueError("no JSON object")
    # take the first balanced object
    depth = 0
    start = m.start()
    end = None
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    obj = json.loads(text[start:end])
    scores = obj.get("scores") or {}
    clean: dict[str, int] = {}
    for d in DIM_IDS:
        v = scores.get(d)
        if not isinstance(v, int) or not 1 <= v <= 4:
            raise ValueError(f"bad score for {d}: {v!r}")
        clean[d] = v
    tags = [t for t in (obj.get("error_tags") or []) if t in TAG_IDS]
    if "none" in tags and len(tags) > 1:
        tags = [t for t in tags if t != "none"]
    rationale = {k: str(v) for k, v in (obj.get("rationale") or {}).items() if k in DIM_IDS}
    return clean, tags, rationale, str(obj.get("overall_comment", ""))


def judge_trace(client: ModelClient, trace: Trace, rendered_inputs: str, judge_model: str, seed: int = 7, effort: str = "high") -> JudgeRecord:
    """Blind judging: the judge sees only the rendered variant inputs, the raw reasoning and the answer."""
    user = USER_TEMPLATE.format(render=rendered_inputs, reasoning=trace.reasoning, answer=trace.answer)
    rec = JudgeRecord(trace_key=trace.trace_key, judge_model=judge_model, judge_prompt_id=PROMPT_ID)
    attempts = 0
    last_err = None
    system = SYSTEM
    for attempt in range(2):
        attempts += 1
        try:
            resp = client.generate(GenerateRequest(system=system, user=user, effort=effort, seed=seed, temperature=0.0, max_tokens=1500))
        except ClientError as e:
            last_err = f"client: {e}"
            break
        rec.raw = resp.answer
        rec.meta = {"latency_ms": resp.latency_ms, "usage": resp.usage, "attempts": attempts}
        try:
            rec.scores, rec.error_tags, rec.rationale, rec.overall_comment = parse_judge_output(resp.answer)
            rec.error = None
            return rec
        except (ValueError, json.JSONDecodeError) as e:
            last_err = f"unparseable: {e}"
            system = SYSTEM + "\n\nReturn only the JSON object."
    rec.error = last_err or "unparseable"
    rec.meta = {**rec.meta, "attempts": attempts}
    return rec


def run_judge(run_dir: str | Path, cases: list[Case], perturbations: list[Perturbation], client: ModelClient, judge_model: str,
              keys: set[str] | None = None, lexicon: Lexicon | None = None, repeats: dict[str, int] | None = None,
              progress=None) -> int:
    """Judge traces (all, or the given trace_keys) and write judge.jsonl. `repeats` maps trace_key -> extra repeats for reliability."""
    from . import perturb
    lx = lexicon or lex_mod.load()
    run_dir = Path(run_dir)
    traces = load_traces(run_dir / "traces.jsonl")
    case_by = {c.case_id: c for c in cases}
    pert_by = {(p.case_id, p.variant): p for p in perturbations}
    renders: dict[tuple[str, str], str] = {}
    out: list[JudgeRecord] = []
    for t in sorted(traces, key=lambda t: t.trace_key):
        if not t.ok or (keys is not None and t.trace_key not in keys):
            continue
        key = (t.case_id, t.variant)
        if key not in renders:
            c = case_by[t.case_id]
            renders[key] = c.render() if t.variant == "base" else perturb.apply(c, pert_by[key], lx, verify=False).render()
        n = 1 + (repeats or {}).get(t.trace_key, 0)
        for i in range(n):
            rec = judge_trace(client, t, renders[key], judge_model, seed=7 + i)
            if i:
                rec.extra["repeat"] = i
            out.append(rec)
            if progress:
                progress(f"judged {t.trace_key}{' repeat ' + str(i) if i else ''} {'ok' if not rec.error else rec.error}")
    write_jsonl(run_dir / "judge.jsonl", out)
    return len(out)


class LLMVerifier:
    """Knowledge-claim verifier against retrieved WHO text using the judge client (spec 04 §5, 11 §6)."""

    name = "llm"
    version = "1"

    def __init__(self, client: ModelClient):
        self.client = client

    def verify(self, claim: Claim, trace: Trace, lexicon: Lexicon) -> KnowledgeCheck | None:
        if not trace.retrieved:
            return KnowledgeCheck("abstain", self.name, "no retrieved text")
        ctx = "\n\n".join(r.text for r in trace.retrieved[:6])
        user = f"Reference text:\n{ctx}\n\nClaim: {claim.text}\n\nIs the claim supported by the reference text? Answer with one word: supported, contradicted, or not_addressed."
        try:
            resp = self.client.generate(GenerateRequest(system="You check medical claims against reference text. Answer with one word.",
                                                        user=user, effort="low", seed=1, temperature=0.0, max_tokens=10))
        except ClientError as e:
            return KnowledgeCheck("abstain", self.name, f"client error: {e}")
        ans = (resp.answer or "").strip().lower()
        verdict = "consistent" if ans.startswith("supported") else "inconsistent" if ans.startswith("contradicted") else "abstain"
        return KnowledgeCheck(verdict, self.name, ans[:80])
