"""Viewer bundle export, reasoning map, ratings import (spec 12, 13 §8)."""
from __future__ import annotations

import difflib
import json
import random
import shutil
from collections import defaultdict
from pathlib import Path

from . import extract, judge, perturb
from . import lexicon as lex_mod
from .experiment import read_manifest
from .lexicon import Lexicon
from .schema import Case, Claim, Perturbation, load_claims, load_traces, read_jsonl, write_jsonl

BUNDLE_VERSION = 1
INDEX_LIMIT = 2 * 1024 * 1024


def report_diff(base: str, variant: str) -> list[dict]:
    sm = difflib.SequenceMatcher(None, base, variant, autojunk=False)
    out = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        out.append({"op": tag, "base_span": [i1, i2], "variant_span": [j1, j2], "before": base[i1:i2], "after": variant[j1:j2]})
    return out


def build_map(claims: list[Claim], answer_entity: str, lx: Lexicon) -> dict:
    """Heuristic reasoning graph (spec 13 §8)."""
    nodes = []
    index = {}
    for c in claims:
        if c.type not in ("factual", "inferential", "knowledge"):
            continue
        findings = sorted({a.finding_id for a in c.assertions})
        node = {"id": f"c{c.claim_id}", "claim_id": c.claim_id, "type": c.type, "label": c.label, "flags": c.flags,
                "text": (c.text[:117] + "…") if len(c.text) > 120 else c.text, "findings": findings, "entities": c.entities,
                "paragraph_id": c.paragraph_id}
        index[c.claim_id] = node
        nodes.append(node)
    answer_node = {"id": "answer", "type": "answer", "label": None, "text": lx.entity_display(answer_entity) if answer_entity in lx.entities else answer_entity,
                   "entities": [answer_entity], "findings": [], "paragraph_id": None, "claim_id": None, "flags": []}
    edges = []
    seen = set()

    def add(src, dst, kind, weak=False):
        k = (src, dst, kind)
        if k not in seen and src != dst:
            seen.add(k)
            e = {"source": src, "target": dst, "kind": kind}
            if weak:
                e["weak"] = True
            edges.append(e)

    asserted_by: dict[str, list[dict]] = defaultdict(list)
    for n in nodes:
        if n["type"] == "factual":
            for f in n["findings"]:
                asserted_by[f].append(n)
    ordered = sorted(nodes, key=lambda n: n["claim_id"])
    for i, n in enumerate(ordered):
        if n["type"] == "inferential":
            # evidence edges
            mentioned = set(n["findings"])
            cl = next(c for c in claims if c.claim_id == n["claim_id"])
            for fid in lx.findings:
                if lx.mentions_marker(cl.text, fid):
                    mentioned.add(fid)
            for f in mentioned:
                for src in asserted_by.get(f, []):
                    if src["claim_id"] < n["claim_id"]:
                        add(src["id"], n["id"], "evidence")
            # knowledge support
            for k in ordered:
                if k["type"] == "knowledge" and k["claim_id"] < n["claim_id"] and k["paragraph_id"] is not None \
                        and n["paragraph_id"] is not None and n["paragraph_id"] - k["paragraph_id"] <= 1:
                    if set(k["findings"]) & mentioned or set(k["entities"]) & set(n["entities"]):
                        add(k["id"], n["id"], "knowledge")
            # chain
            if i > 0 and ordered[i - 1]["type"] == "inferential" and ordered[i - 1]["paragraph_id"] == n["paragraph_id"] \
                    and lx.has_phrase("inference", cl.text):
                add(ordered[i - 1]["id"], n["id"], "chain")
            if answer_entity in n["entities"]:
                add(n["id"], "answer", "conclusion")
    if not any(e["kind"] == "conclusion" for e in edges):
        infs = [n for n in ordered if n["type"] == "inferential"]
        if infs:
            add(infs[-1]["id"], "answer", "conclusion", weak=True)
    incoming = {e["target"] for e in edges if e["kind"] in ("evidence", "knowledge", "chain")}
    for n in nodes:
        n["break"] = n["type"] == "inferential" and n["id"] not in incoming
    answer_node["break"] = all(e.get("weak") for e in edges if e["kind"] == "conclusion") if edges else True
    nodes.append(answer_node)
    return {"nodes": nodes, "edges": edges, "heuristic": True}


def to_viewer(run_dir: str | Path, out_dir: str | Path, cases: list[Case], perturbations: list[Perturbation], shard: bool = True,
              include_raw: bool = False, study: dict | None = None, lexicon: Lexicon | None = None, redact_prompt: bool = False,
              ratings: list[dict] | None = None, with_viewer: Path | None = None) -> Path:
    lx = lexicon or lex_mod.load()
    run_dir = Path(run_dir)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = read_manifest(run_dir)
    if redact_prompt:
        manifest = {**manifest, "prompt": {k: v for k, v in manifest["prompt"].items() if k in ("id", "sha256")}}
    traces = load_traces(run_dir / "traces.jsonl")
    claims_by: dict[str, list[Claim]] = defaultdict(list)
    if (run_dir / "claims.jsonl").exists():
        for c in load_claims(run_dir / "claims.jsonl"):
            claims_by[c.trace_key].append(c)
    def load_map(name):
        p = run_dir / name
        return {r["trace_key"]: r for r in read_jsonl(p)} if p.exists() else {}
    grounding = load_map("grounding.jsonl")
    cf = load_map("counterfactual.jsonl")
    au = load_map("authority.jsonl")
    jd = load_map("judge.jsonl")
    summary = json.loads((run_dir / "summary.json").read_text()) if (run_dir / "summary.json").exists() else None
    pert_by_case: dict[str, list[Perturbation]] = defaultdict(list)
    for p in perturbations:
        pert_by_case[p.case_id].append(p)
    traces_by_case: dict[str, list] = defaultdict(list)
    for t in traces:
        traces_by_case[t.case_id].append(t)
    index_cases = []
    case_files: dict[str, dict] = {}
    for c in cases:
        ts = traces_by_case.get(c.case_id, [])
        if not ts:
            continue
        variants: dict[str, dict] = {"base": {"variant": "base", "kind": "base", "reports": c.reports, "truth_after": c.truth, "perturbation": None, "diff": {},
                                              "finding_spans": extract.finding_spans(c, lx)}}
        for p in pert_by_case.get(c.case_id, []):
            v = perturb.apply(c, p, lx, verify=False)
            variants[p.variant] = {
                "variant": p.variant, "kind": p.kind, "reports": v.reports, "truth_after": p.truth_after,
                "perturbation": {"primary_finding": p.primary_finding, "edits": [e.to_dict() for e in p.edits], "linked_findings": p.linked_findings,
                                 "expected_entity": p.expected_entity, "expected_behaviour": p.expected_behaviour,
                                 "cue": p.cue.to_dict() if p.cue else None, "rationale": p.rationale, "flags": p.flags},
                "diff": {k: report_diff(c.reports.get(k, ""), v.reports.get(k, "")) for k in c.reports if c.reports.get(k, "") != v.reports.get(k, "")},
                "finding_spans": extract.finding_spans(v, lx),
            }
        trace_objs = []
        base_ref: dict = {}
        for t in sorted(ts, key=lambda t: t.trace_key):
            g = grounding.get(t.trace_key)
            d = {"trace_key": t.trace_key, "variant": t.variant, "effort": t.effort, "run": t.run, "reasoning": t.reasoning, "answer": t.answer,
                 "retrieved": [r.to_dict() for r in t.retrieved], "meta": {k: v for k, v in t.meta.to_dict().items() if k != "schema_version"},
                 "claims": [cl.to_dict() for cl in claims_by.get(t.trace_key, [])], "grounding": g,
                 "counterfactual": cf.get(t.trace_key), "authority": au.get(t.trace_key), "judge": jd.get(t.trace_key)}
            if include_raw:
                d["raw"] = t.raw
            d["map"] = build_map(claims_by.get(t.trace_key, []), (g or {}).get("answer_entity", "UNRESOLVED"), lx) if claims_by.get(t.trace_key) else None
            r = cf.get(t.trace_key) or au.get(t.trace_key)
            if r:
                base_ref[t.effort] = {"base_modal_entity": r["base_modal_entity"], "base_mode_share": r.get("base_mode_share"),
                                      "base_stable": r["base_stable"], "base_n": r.get("base_n")}
            trace_objs.append(d)
        case_obj = {"case": {"case_id": c.case_id, "entity": c.entity, "subtype": c.subtype, "flags": c.flags.to_dict(), "reports": c.reports,
                             "truth": c.truth, "finding_spans": variants["base"]["finding_spans"]},
                    "variants": variants, "traces": trace_objs, "base_reference": base_ref}
        case_files[c.case_id] = case_obj
        index_cases.append({"case_id": c.case_id, "entity": c.entity, "subtype": c.subtype, "flags": c.flags.to_dict(),
                            "variants": list(variants), "n_traces": len(trace_objs), "file": f"cases/{c.case_id}.json"})
    index = {
        "bundle_version": BUNDLE_VERSION,
        "run": {"run_id": manifest.get("run_id"), "manifest": manifest},
        "lexicon": {"version": lx.version,
                    "entities": [{"id": e["id"], "display": e["display"], "in_scope": e["in_scope"], "parent": e.get("parent")} for e in lx.data["entities"]],
                    "findings": [{"id": f["id"], "display": f["display"], "kind": f["kind"]} for f in lx.data["findings"]],
                    # Discriminator table (finding -> entity -> pos|neg|var) and linked findings, for the viewer's
                    # Lexicon Atlas and hallucination heatmap (spec 13 §7; viewer design brief §4.1).
                    "discriminators": lx.data.get("discriminators", {}),
                    "linked": lx.data.get("linked", {})},
        "rubric": {"dimensions": judge.RUBRIC, "error_tags": judge.ERROR_TAGS},
        "cases": index_cases, "summary": summary, "study": study,
    }
    if ratings is not None:
        index["ratings"] = ratings
    if shard:
        (out_dir / "cases").mkdir(exist_ok=True)
        for cid, obj in case_files.items():
            (out_dir / "cases" / f"{cid}.json").write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
        text = json.dumps(index, ensure_ascii=False)
        if len(text.encode("utf-8")) > INDEX_LIMIT:
            raise ValueError(f"index.json exceeds {INDEX_LIMIT} bytes")
        (out_dir / "index.json").write_text(text, encoding="utf-8")
    else:
        for ic in index["cases"]:
            ic.pop("file", None)
        (out_dir / "bundle.json").write_text(json.dumps({"index": index, "cases": case_files}, ensure_ascii=False), encoding="utf-8")
    (out_dir / "ratings-schema.json").write_text(json.dumps(RATINGS_SCHEMA, indent=1), encoding="utf-8")
    (out_dir / "figures").mkdir(exist_ok=True)
    if with_viewer and Path(with_viewer).exists():
        for item in Path(with_viewer).iterdir():
            dest = out_dir / item.name
            if item.is_dir():
                shutil.copytree(item, dest, dirs_exist_ok=True)
            else:
                shutil.copy2(item, dest)
    return out_dir


RATINGS_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema", "title": "traceaudit rating record", "type": "object",
    "required": ["schema_version", "study_id", "rater_id", "trace_key", "dimension", "submitted_at", "blinded"],
    "properties": {
        "schema_version": {"const": 1}, "study_id": {"type": "string"}, "rater_id": {"type": "string", "pattern": "^R\\d{2}$"},
        "session_id": {"type": ["string", "null"]}, "trace_key": {"type": "string"}, "presentation_index": {"type": ["integer", "null"]},
        "dimension": {"type": "string", "enum": ["D1", "D2", "D3", "D4", "D5", "D6", "D7", "tags"]},
        "score": {"type": ["integer", "null"], "minimum": 1, "maximum": 4}, "error_tags": {"type": ["array", "null"], "items": {"type": "string"}},
        "comment": {"type": ["string", "null"]}, "started_at": {"type": ["string", "null"]}, "submitted_at": {"type": "string"},
        "duration_ms": {"type": ["integer", "null"]}, "blinded": {"type": "boolean"}, "viewer_version": {"type": ["string", "null"]},
        "bundle_run_id": {"type": ["string", "null"]},
    },
}


def validate_rating(d: dict) -> list[str]:
    probs = []
    for k in RATINGS_SCHEMA["required"]:
        if k not in d:
            probs.append(f"missing {k}")
    if d.get("dimension") not in RATINGS_SCHEMA["properties"]["dimension"]["enum"]:
        probs.append(f"bad dimension {d.get('dimension')!r}")
    if d.get("dimension") != "tags" and not (isinstance(d.get("score"), int) and 1 <= d["score"] <= 4):
        probs.append(f"bad score {d.get('score')!r}")
    if d.get("dimension") == "tags" and any(t not in judge.TAG_IDS for t in (d.get("error_tags") or [])):
        probs.append("unknown error tag")
    import re
    if not re.match(r"^R\d{2}$", str(d.get("rater_id", ""))):
        probs.append("bad rater_id")
    return probs


def import_ratings(src: str | Path, dest_dir: str | Path, allow_unblinded: bool = False) -> tuple[int, list[str]]:
    """Validate, de-duplicate (latest submitted_at wins) and append into ratings/<study>/<rater>.jsonl."""
    dest_dir = Path(dest_dir)
    problems: list[str] = []
    latest: dict[tuple, dict] = {}
    for i, d in enumerate(read_jsonl(src)):
        p = validate_rating(d)
        if not d.get("blinded", True) and not allow_unblinded:
            p.append("unblinded rating refused")
        if p:
            problems.append(f"line {i + 1}: {'; '.join(p)}")
            continue
        k = (d["trace_key"], d["rater_id"], d["dimension"])
        if k not in latest or d["submitted_at"] > latest[k]["submitted_at"]:
            latest[k] = d
    by_file: dict[Path, list[dict]] = defaultdict(list)
    for d in latest.values():
        by_file[dest_dir / d["study_id"] / f"{d['rater_id']}.jsonl"].append(d)
    n = 0
    for path, recs in by_file.items():
        existing = {(r["trace_key"], r["rater_id"], r["dimension"]): r for r in read_jsonl(path)} if path.exists() else {}
        for r in recs:
            k = (r["trace_key"], r["rater_id"], r["dimension"])
            if k not in existing or r["submitted_at"] > existing[k]["submitted_at"]:
                existing[k] = r
        write_jsonl(path, sorted(existing.values(), key=lambda r: (r["trace_key"], r["dimension"])))
        n += len(recs)
    return n, problems


def select_rating_set(grounding_path: str | Path, n: int, seed: int, case_entities: dict[str, str]) -> list[str]:
    """Stratified sample of trace_keys: entity × kind(base, decisive, anchor_loss, wrong cue) × effort (spec 15 §4)."""
    from .schema import variant_kind
    recs = [r for r in read_jsonl(grounding_path) if not r.get("error")]
    strata: dict[tuple, list[str]] = defaultdict(list)
    for r in recs:
        kind = variant_kind(r["variant"])
        if kind == "authority" and not r["variant"].startswith("auth-wrong"):
            continue
        if kind == "neutral":
            continue
        strata[(case_entities.get(r["case_id"], "?"), kind, r["effort"])].append(r["trace_key"])
    rng = random.Random(seed)
    keys = sorted(strata)
    for k in keys:
        rng.shuffle(strata[k])
    out: list[str] = []
    while len(out) < n and any(strata.values()):
        for k in keys:
            if strata[k] and len(out) < n:
                out.append(strata[k].pop())
    return sorted(out)


def figures_check(bundle_dir: str | Path, summary_path: str | Path) -> list[str]:
    """Each figures/<name>.json must be a subset of summary.json values."""
    summary = json.loads(Path(summary_path).read_text())
    problems = []
    for p in sorted(Path(bundle_dir, "figures").glob("*.json")):
        data = json.loads(p.read_text())
        for path in data.get("summary_paths", []):
            node = summary
            try:
                for part in path.split("."):
                    node = node[part]
            except (KeyError, TypeError):
                problems.append(f"{p.name}: summary path {path} missing")
    return problems
