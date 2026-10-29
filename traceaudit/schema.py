"""Record types, identifiers, trace_key, JSONL I/O and validation (spec 01)."""
from __future__ import annotations

import dataclasses
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Iterator, TypeVar

from . import SCHEMA_VERSION

REPORT_KEYS = ("clinical", "morphology", "flow_cytometry", "cytogenetics", "molecular")
REPORT_TITLES = {
    "clinical": "Clinical summary",
    "morphology": "Morphology",
    "flow_cytometry": "Flow cytometry",
    "cytogenetics": "Cytogenetics",
    "molecular": "Molecular",
}
EFFORTS = ("low", "medium", "high")
# Entity ids come from the lexicon in use. These are the reference (haematology) domain's, kept for the
# study's documentation and tests; the engine never requires them.
IN_SCOPE_ENTITIES = ("CLL_SLL", "MCL", "FL", "HCL", "LPL", "MZL")
ANSWER_ONLY_ENTITIES = ("MBL", "SBLPN", "DLBCL", "OTHER", "UNRESOLVED")
ENTITIES = IN_SCOPE_ENTITIES + ANSWER_ONLY_ENTITIES
VARIANT_KINDS = ("base", "decisive", "neutral", "anchor_loss", "authority", "ablation")

CASE_ID_RE = re.compile(r"^[A-Z]{2,5}-\d{3}$")
VARIANT_RE = re.compile(r"^(base|(dec|neu|anc|auth|abl)-[a-z0-9_]+(-[a-z0-9_]+)*)$")
FINDING_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
RATER_ID_RE = re.compile(r"^R\d{2}$")
RUN_ID_RE = re.compile(r"^\d{8}T\d{6}Z-[a-z0-9]{6}$")

PROBLEM_CODES = (
    "C1_TRUTH_MISMATCH", "C2_POLARITY_CONFLICT", "C3_BAD_ID", "C4_MISSING_REPORT", "C5_BAD_ENTITY",
    "C6_INCOMPLETE_FLAG", "C7_BAD_TRUTH_VALUE", "C8_UNKNOWN_FINDING",
    "P1_TRUTH_AFTER_MISMATCH", "P2_BAD_KIND", "P3_PRIMARY_MISSING", "P4_BAD_VARIANT", "P5_CASE_MISSING",
    "P6_CUE_MISSING", "P7_APPLY_FAILED",
    "T1_BAD_KEY", "T2_BAD_EFFORT", "T3_KEY_MISMATCH",
)


# --------------------------------------------------------------------------- helpers

def make_trace_key(case_id: str, variant: str, effort: str, run: int) -> str:
    for part in (case_id, variant, effort):
        if "|" in part:
            raise ValueError(f"trace_key component contains '|': {part!r}")
    return f"{case_id}|{variant}|{effort}|{run}"


def parse_trace_key(key: str) -> tuple[str, str, str, int]:
    parts = key.split("|")
    if len(parts) != 4:
        raise ValueError(f"bad trace_key: {key!r}")
    case_id, variant, effort, run = parts
    return case_id, variant, effort, int(run)


def variant_kind(variant: str) -> str:
    if variant == "base":
        return "base"
    prefix = variant.split("-", 1)[0]
    return {"dec": "decisive", "neu": "neutral", "anc": "anchor_loss", "auth": "authority", "abl": "ablation"}.get(prefix, "unknown")


T = TypeVar("T", bound="Record")


class Record:
    """Mixin: dict round-trip preserving unknown keys in `extra`."""

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {}
        for f in dataclasses.fields(self):  # type: ignore[arg-type]
            if f.name == "extra":
                continue
            d[f.name] = _to_plain(getattr(self, f.name))
        d.update(getattr(self, "extra", {}) or {})
        d.setdefault("schema_version", SCHEMA_VERSION)
        return d

    @classmethod
    def from_dict(cls: type[T], d: dict[str, Any]) -> T:
        names = {f.name for f in dataclasses.fields(cls)}  # type: ignore[arg-type]
        sv = d.get("schema_version", SCHEMA_VERSION)
        if sv > SCHEMA_VERSION:
            raise ValueError(f"schema_version {sv} newer than supported {SCHEMA_VERSION}")
        kwargs: dict[str, Any] = {}
        extra: dict[str, Any] = {}
        for k, v in d.items():
            if k in names and k != "extra":
                kwargs[k] = v
            elif k != "schema_version":
                extra[k] = v
        obj = cls(**_coerce(cls, kwargs))  # type: ignore[arg-type]
        if "extra" in names:
            object.__setattr__(obj, "extra", extra)
        return obj

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=False)

    @classmethod
    def from_json(cls: type[T], s: str) -> T:
        return cls.from_dict(json.loads(s))


def _to_plain(v: Any) -> Any:
    if dataclasses.is_dataclass(v) and not isinstance(v, type):
        if isinstance(v, Record):
            d = v.to_dict()
            d.pop("schema_version", None)
            return d
        return {f.name: _to_plain(getattr(v, f.name)) for f in dataclasses.fields(v)}
    if isinstance(v, (list, tuple)):
        return [_to_plain(x) for x in v]
    if isinstance(v, dict):
        return {k: _to_plain(x) for k, x in v.items()}
    return v


_NESTED: dict[tuple[str, str], Any] = {}


def _coerce(cls: type, kwargs: dict[str, Any]) -> dict[str, Any]:
    for (owner, fname), spec in _NESTED.items():
        if owner != cls.__name__ or fname not in kwargs or kwargs[fname] is None:
            continue
        sub, many = spec
        val = kwargs[fname]
        if many:
            kwargs[fname] = [sub.from_dict(x) if isinstance(x, dict) else x for x in val]
        elif isinstance(val, dict):
            kwargs[fname] = sub.from_dict(val)
    return kwargs


def _nested(owner: str, fname: str, sub: type, many: bool = False) -> None:
    _NESTED[(owner, fname)] = (sub, many)


# --------------------------------------------------------------------------- records

@dataclass
class Review(Record):
    reviewer_id: str | None = None
    date: str | None = None
    status: str = "draft"  # draft | approved | rejected
    notes: str = ""
    extra: dict = field(default_factory=dict, repr=False, compare=False)


@dataclass
class Flags(Record):
    discordant: bool = False
    incomplete: bool = False
    atypical_features: list[str] = field(default_factory=list)
    missing_modalities: list[str] = field(default_factory=list)
    extra: dict = field(default_factory=dict, repr=False, compare=False)


@dataclass
class Provenance(Record):
    generator_version: str | None = None
    template_id: str | None = None
    seed: int | None = None
    paraphrase_model: str | None = None
    extra: dict = field(default_factory=dict, repr=False, compare=False)


@dataclass
class Case(Record):
    case_id: str
    entity: str
    reports: dict[str, str]
    truth: dict[str, str]
    subtype: str | None = None
    flags: Flags = field(default_factory=Flags)
    provenance: Provenance = field(default_factory=Provenance)
    review: Review = field(default_factory=Review)
    variant: str = "base"
    sections: list[dict] | None = None   # [{id, title}] when the case uses documents other than the default five
    extra: dict = field(default_factory=dict, repr=False, compare=False)

    def section_list(self) -> list[tuple[str, str]]:
        if self.sections:
            return [(s["id"], s.get("title") or s["id"].replace("_", " ").capitalize()) for s in self.sections]
        return [(k, REPORT_TITLES[k]) for k in REPORT_KEYS]

    def section_list_dicts(self) -> list[dict]:
        return [{"id": k, "title": t} for k, t in self.section_list()]

    def render(self) -> str:
        parts = []
        for key, title in self.section_list():
            body = (self.reports.get(key) or "").strip()
            parts.append(f"## {title}\n{body if body else 'Not performed.'}")
        return "\n\n".join(parts) + "\n"

    def report_offsets(self) -> dict[str, int]:
        """Offset of each report body inside render()."""
        offs = {}
        pos = 0
        for key, title in self.section_list():
            head = f"## {title}\n"
            pos += len(head)
            offs[key] = pos
            body = (self.reports.get(key) or "").strip()
            pos += len(body if body else "Not performed.") + 2
        return offs

    def copy(self) -> "Case":
        return Case.from_dict(json.loads(self.to_json()))


_nested("Case", "flags", Flags)
_nested("Case", "provenance", Provenance)
_nested("Case", "review", Review)


@dataclass
class Edit(Record):
    finding_id: str | None
    from_: str | None = None
    to: str | None = None
    role: str = "primary"  # primary | co_edit | neutral
    report: str | None = None
    op: str | None = None  # neutral op name
    value_after: str | None = None
    inserted: bool = False
    rewrites: list[dict] = field(default_factory=list)
    extra: dict = field(default_factory=dict, repr=False, compare=False)

    def to_dict(self) -> dict[str, Any]:
        d = super().to_dict()
        d["from"] = d.pop("from_")
        d.pop("schema_version", None)
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Edit":
        d = dict(d)
        if "from" in d:
            d["from_"] = d.pop("from")
        return super().from_dict(d)  # type: ignore[return-value]


@dataclass
class Cue(Record):
    entity: str
    correct: bool
    text: str
    template_id: str = "referrer-v1"
    report: str = "clinical"
    position: str = "end"
    extra: dict = field(default_factory=dict, repr=False, compare=False)


@dataclass
class Perturbation(Record):
    perturbation_id: str
    case_id: str
    variant: str
    kind: str
    edits: list[Edit] = field(default_factory=list)
    primary_finding: str | None = None
    linked_findings: list[str] = field(default_factory=list)
    expected_entity: str | None = None
    expected_behaviour: str | None = None
    cue: Cue | None = None
    truth_after: dict[str, str] = field(default_factory=dict)
    rationale: str = ""
    flags: list[str] = field(default_factory=list)
    review: Review = field(default_factory=Review)
    extra: dict = field(default_factory=dict, repr=False, compare=False)

    @property
    def co_edits(self) -> list[str]:
        return [e.finding_id for e in self.edits if e.role == "co_edit" and e.finding_id]

    @property
    def edited_findings(self) -> list[str]:
        return [e.finding_id for e in self.edits if e.finding_id]


_nested("Perturbation", "edits", Edit, many=True)
_nested("Perturbation", "cue", Cue)
_nested("Perturbation", "review", Review)


@dataclass
class Retrieved(Record):
    doc_id: str | None = None
    chunk_id: int | str | None = None
    text: str = ""
    score: float | None = None
    extra: dict = field(default_factory=dict, repr=False, compare=False)


@dataclass
class TraceMeta(Record):
    seed: int | None = None
    temperature: float | None = None
    latency_ms: int | None = None
    usage: dict = field(default_factory=dict)
    timestamp: str | None = None
    finish_reason: str | None = None
    parse_warnings: list[str] = field(default_factory=list)
    error: str | None = None
    extra: dict = field(default_factory=dict, repr=False, compare=False)


@dataclass
class Trace(Record):
    trace_key: str
    case_id: str
    variant: str
    effort: str
    run: int
    model: str
    reasoning: str
    answer: str
    server: str | None = None
    prompt_id: str | None = None
    retrieved: list[Retrieved] = field(default_factory=list)
    raw: str = ""
    meta: TraceMeta = field(default_factory=TraceMeta)
    extra: dict = field(default_factory=dict, repr=False, compare=False)

    @property
    def kind(self) -> str:
        return variant_kind(self.variant)

    @property
    def ok(self) -> bool:
        return self.meta.error is None


_nested("Trace", "retrieved", Retrieved, many=True)
_nested("Trace", "meta", TraceMeta)


@dataclass(frozen=True)
class Assertion:
    finding_id: str
    polarity: str | None  # pos | neg | None (mention)
    start: int
    end: int
    surface: str
    cue_start: int
    cue_end: int
    rule: str  # phrase | numeric | suffix | pre | post | noun | default | none
    intensity: str | None = None
    warnings: tuple[str, ...] = ()
    report: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d = dataclasses.asdict(self)
        d["warnings"] = list(self.warnings)
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Assertion":
        d = dict(d)
        d["warnings"] = tuple(d.get("warnings", ()))
        return cls(**{k: v for k, v in d.items() if k in {f.name for f in dataclasses.fields(cls)}})


@dataclass
class Evidence(Record):
    finding_id: str
    claimed: str | None
    truth: str | None
    report: str | None = None
    span: list[int] | None = None
    extra: dict = field(default_factory=dict, repr=False, compare=False)


@dataclass
class KnowledgeCheck(Record):
    verdict: str  # consistent | inconsistent | abstain
    verifier: str
    evidence: str | None = None
    confidence: float | None = None
    extra: dict = field(default_factory=dict, repr=False, compare=False)


@dataclass
class Claim(Record):
    trace_key: str
    claim_id: int
    paragraph_id: int
    start: int
    end: int
    text: str
    type: str  # factual | knowledge | inferential | other
    flags: list[str] = field(default_factory=list)
    assertions: list[Assertion] = field(default_factory=list)
    label: str | None = None  # supported | contradicted | unsupported | ambiguous
    evidence: list[Evidence] = field(default_factory=list)
    knowledge_check: KnowledgeCheck | None = None
    entities: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    extra: dict = field(default_factory=dict, repr=False, compare=False)

    def to_dict(self) -> dict[str, Any]:
        d = super().to_dict()
        d["assertions"] = [a.to_dict() for a in self.assertions]
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Claim":
        d = dict(d)
        d["assertions"] = [Assertion.from_dict(a) if isinstance(a, dict) else a for a in d.get("assertions", [])]
        return super().from_dict(d)  # type: ignore[return-value]


_nested("Claim", "evidence", Evidence, many=True)
_nested("Claim", "knowledge_check", KnowledgeCheck)


@dataclass
class GroundingRecord(Record):
    trace_key: str
    case_id: str
    variant: str
    effort: str
    run: int
    n_claims: int = 0
    n_factual: int = 0
    n_knowledge: int = 0
    n_inferential: int = 0
    n_other: int = 0
    n_supported: int = 0
    n_contradicted: int = 0
    n_unsupported: int = 0
    n_ambiguous: int = 0
    grounding_rate: float | None = None
    contradicted_findings: list[str] = field(default_factory=list)
    unsupported_findings: list[str] = field(default_factory=list)
    answer_entity: str = "UNRESOLVED"
    answer_entity_raw: str | None = None
    answer_subtype: str | None = None
    answer_hedged: bool = False
    answer_correct: bool | None = None
    trace_conclusion_entity: str | None = None
    trace_answer_agree: bool | None = None
    knowledge_consistent: int = 0
    knowledge_inconsistent: int = 0
    knowledge_abstain: int = 0
    n_has_inference: int = 0
    n_supported_no_inference: int = 0
    n_graded_no_inference: int = 0
    error: str | None = None
    extra: dict = field(default_factory=dict, repr=False, compare=False)


@dataclass
class CounterfactualRecord(Record):
    trace_key: str
    kind: str
    primary_finding: str | None
    co_edits: list[str]
    linked_findings: list[str]
    expected_entity: str | None
    base_modal_entity: str | None
    base_mode_share: float | None
    base_stable: bool
    base_n: int
    answer_entity: str
    answer_hedged: bool
    changed: bool | None
    changed_to_expected: bool | None
    cited_primary: bool
    mentioned_primary: bool
    mentioned_any: bool
    primary_mention_span: list[int] | None
    outcome: str
    flags: list[str] = field(default_factory=list)
    neutral_ops: list[str] = field(default_factory=list)
    extra: dict = field(default_factory=dict, repr=False, compare=False)


@dataclass
class AuthorityRecord(Record):
    trace_key: str
    cue_entity: str
    cue_correct: bool
    base_modal_entity: str | None
    base_stable: bool
    answer_entity: str
    answer_hedged: bool
    acknowledged: bool
    ack_span: list[int] | None
    outcome: str
    held_detail: str | None = None
    flags: list[str] = field(default_factory=list)
    extra: dict = field(default_factory=dict, repr=False, compare=False)


@dataclass
class JudgeRecord(Record):
    trace_key: str
    judge_model: str
    judge_prompt_id: str
    scores: dict[str, int] = field(default_factory=dict)
    error_tags: list[str] = field(default_factory=list)
    rationale: dict[str, str] = field(default_factory=dict)
    overall_comment: str = ""
    raw: str = ""
    meta: dict = field(default_factory=dict)
    error: str | None = None
    extra: dict = field(default_factory=dict, repr=False, compare=False)


@dataclass
class Rating(Record):
    study_id: str
    rater_id: str
    trace_key: str
    dimension: str
    score: int | None
    session_id: str | None = None
    presentation_index: int | None = None
    error_tags: list[str] | None = None
    comment: str | None = None
    started_at: str | None = None
    submitted_at: str | None = None
    duration_ms: int | None = None
    blinded: bool = True
    viewer_version: str | None = None
    bundle_run_id: str | None = None
    extra: dict = field(default_factory=dict, repr=False, compare=False)


@dataclass
class Problem:
    code: str
    path: str
    message: str
    severity: str = "error"

    def __str__(self) -> str:
        return f"[{self.severity}] {self.code} {self.path}: {self.message}"


# --------------------------------------------------------------------------- JSONL I/O

def read_jsonl(path: str | Path) -> Iterator[dict[str, Any]]:
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def write_jsonl(path: str | Path, records: Iterable[Any], append: bool = False) -> int:
    n = 0
    mode = "a" if append else "w"
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, mode, encoding="utf-8") as f:
        for r in records:
            d = r.to_dict() if hasattr(r, "to_dict") else r
            f.write(json.dumps(d, ensure_ascii=False) + "\n")
            n += 1
    return n


def load_cases(path: str | Path) -> list[Case]:
    return [Case.from_dict(d) for d in read_jsonl(path)]


def load_perturbations(path: str | Path) -> list[Perturbation]:
    return [Perturbation.from_dict(d) for d in read_jsonl(path)]


def load_traces(path: str | Path) -> list[Trace]:
    return [Trace.from_dict(d) for d in read_jsonl(path)]


def load_claims(path: str | Path) -> list[Claim]:
    return [Claim.from_dict(d) for d in read_jsonl(path)]


# --------------------------------------------------------------------------- validation

def validate_case(case: Case, lexicon=None) -> list[Problem]:
    from . import extract  # lazy to avoid cycle
    from . import lexicon as lex_mod

    lex = lexicon or lex_mod.load()
    probs: list[Problem] = []
    p = f"case[{case.case_id}]"
    if not CASE_ID_RE.match(case.case_id):
        probs.append(Problem("C3_BAD_ID", p, f"case_id {case.case_id!r} does not match grammar"))
    if case.entity not in IN_SCOPE_ENTITIES and case.entity not in lex.entities:
        probs.append(Problem("C5_BAD_ENTITY", p, f"entity {case.entity!r} not in the lexicon"))
    keys = [k for k, _ in case.section_list()]
    for k in keys:
        if k not in case.reports:
            probs.append(Problem("C4_MISSING_REPORT", p, f"report {k!r} missing"))
    missing = [k for k in keys if not (case.reports.get(k) or "").strip()]
    if missing and not case.flags.incomplete:
        probs.append(Problem("C6_INCOMPLETE_FLAG", p, f"empty reports {missing} but flags.incomplete is false"))
    if set(case.flags.missing_modalities) != set(missing):
        probs.append(Problem("C6_INCOMPLETE_FLAG", p, f"flags.missing_modalities {case.flags.missing_modalities} != {missing}",
                             "warning" if not missing else "error"))
    for fid, pol in case.truth.items():
        if pol not in ("pos", "neg"):
            probs.append(Problem("C7_BAD_TRUTH_VALUE", f"{p}.truth.{fid}", f"value {pol!r}"))
        if fid not in lex.findings:
            probs.append(Problem("C8_UNKNOWN_FINDING", f"{p}.truth.{fid}", "finding not in lexicon"))
    try:
        found = extract.findings(case.render(), lex)
    except extract.PolarityConflict as e:
        probs.append(Problem("C2_POLARITY_CONFLICT", p, str(e)))
        return probs
    if found != case.truth:
        extra = {k: v for k, v in found.items() if k not in case.truth}
        missing_t = {k: v for k, v in case.truth.items() if k not in found}
        diff = {k: (case.truth[k], found[k]) for k in case.truth if k in found and case.truth[k] != found[k]}
        probs.append(Problem("C1_TRUTH_MISMATCH", p,
                             f"extracted != truth; extra={extra} missing={missing_t} differ={diff}"))
    return probs


def validate_perturbation(pert: Perturbation, case: Case | None, lexicon=None) -> list[Problem]:
    probs: list[Problem] = []
    p = f"perturbation[{pert.perturbation_id}]"
    if pert.kind not in VARIANT_KINDS or pert.kind == "base":
        probs.append(Problem("P2_BAD_KIND", p, f"kind {pert.kind!r}"))
    if not VARIANT_RE.match(pert.variant) or variant_kind(pert.variant) != pert.kind:
        probs.append(Problem("P4_BAD_VARIANT", p, f"variant {pert.variant!r} inconsistent with kind {pert.kind!r}"))
    if pert.kind in ("decisive", "anchor_loss") and not pert.primary_finding:
        probs.append(Problem("P3_PRIMARY_MISSING", p, "primary_finding required"))
    if pert.kind == "authority" and pert.cue is None:
        probs.append(Problem("P6_CUE_MISSING", p, "cue required"))
    if case is None:
        probs.append(Problem("P5_CASE_MISSING", p, f"case {pert.case_id} not found"))
        return probs
    from . import perturb
    try:
        variant = perturb.apply(case, pert, lexicon=lexicon, verify=True)
    except perturb.PerturbationError as e:
        probs.append(Problem("P7_APPLY_FAILED", p, str(e)))
        return probs
    from . import extract
    found = extract.findings(variant.render(), lexicon)
    if found != pert.truth_after:
        probs.append(Problem("P1_TRUTH_AFTER_MISMATCH", p, f"extracted {found} != truth_after {pert.truth_after}"))
    changed = {k for k in set(case.truth) | set(pert.truth_after) if case.truth.get(k) != pert.truth_after.get(k)}
    if changed != set(pert.edited_findings):
        probs.append(Problem("P1_TRUTH_AFTER_MISMATCH", p, f"changed findings {sorted(changed)} != edits {pert.edited_findings}"))
    return probs


def validate_trace(trace: Trace) -> list[Problem]:
    probs: list[Problem] = []
    p = f"trace[{trace.trace_key}]"
    try:
        cid, var, eff, run = parse_trace_key(trace.trace_key)
    except ValueError as e:
        return [Problem("T1_BAD_KEY", p, str(e))]
    if (cid, var, eff, run) != (trace.case_id, trace.variant, trace.effort, trace.run):
        probs.append(Problem("T3_KEY_MISMATCH", p, "trace_key components disagree with fields"))
    if trace.effort not in EFFORTS:
        probs.append(Problem("T2_BAD_EFFORT", p, f"effort {trace.effort!r}"))
    return probs
