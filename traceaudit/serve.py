"""HTTP service: analyse single traces and run audit jobs behind the viewer (spec 17). Standard library only."""
from __future__ import annotations

import datetime as _dt
import json
import mimetypes
import os
import queue
import random
import re
import shutil
import threading
import time
import traceback
import uuid
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from . import __version__, experiment, export, extract, ledger as ledger_mod, ledger_adapters, lexicon as lex_mod, perturb, pipeline, segment
from .clients import make_client
from .schema import (EFFORTS, Case, Review, Trace, load_cases, load_perturbations, read_jsonl, validate_case,
                     validate_perturbation, write_jsonl)

from .domains import sample_paths as _sample_paths

try:
    SAMPLE_CASES, SAMPLE_PERTS = _sample_paths("haematology")
except Exception:  # noqa: BLE001 - domain pack absent
    SAMPLE_CASES, SAMPLE_PERTS = None, None
MAX_REPORT_CHARS = 50_000
MAX_REASONING_CHARS = 200_000
TERMINAL = {"done", "failed", "cancelled", "interrupted"}


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


# ----------------------------------------------------------------------------- configuration

@dataclass
class ServiceConfig:
    root: Path
    host: str = "127.0.0.1"
    port: int = 8080
    static: Path | None = None
    tokens: dict[str, str] = field(default_factory=dict)      # token -> workspace
    anonymous: str = "analyse"                                   # none | analyse | all
    allow_clients: set[str] = field(default_factory=lambda: {"sim"})
    rate_per_min: int = 60
    extra_cases: Path | None = None
    workers: int = 1
    domain: str | None = None            # packaged domain to offer by default (e.g. "haematology"); None = none built in
    lexicon_path: Path | None = None     # or an explicit default lexicon file
    examples_dir: Path | None = None     # starter lexicons offered as "example:<name>" (default: the repo's examples/)
    operator_keys: dict[str, str] = field(default_factory=dict)   # client kind -> API key held by the operator (from env, never persisted)
    max_calls_per_job: int = 200
    max_calls_per_day: int = 2000

    @classmethod
    def from_args(cls, root: str, host: str, port: int, static: str | None, tokens: str | None, anonymous: str,
                  allow_clients: str, rate_per_min: int, extra_cases: str | None, operator_keys: dict[str, str] | None = None,
                  max_calls_per_job: int = 200, max_calls_per_day: int = 2000, domain: str | None = None, lexicon: str | None = None,
                  examples_dir: str | None = None) -> "ServiceConfig":
        tok: dict[str, str] = {}
        for item in (tokens or "").split(","):
            item = item.strip()
            if not item:
                continue
            t, _, ws = item.partition(":")
            tok[t.strip()] = (ws.strip() or "default")
        if anonymous not in ("none", "analyse", "all"):
            raise ValueError("anonymous must be none, analyse or all")
        return cls(Path(root), host, port, Path(static) if static else None, tok, anonymous,
                   {c.strip() for c in allow_clients.split(",") if c.strip()}, rate_per_min,
                   Path(extra_cases) if extra_cases else None, operator_keys={k: v for k, v in (operator_keys or {}).items() if v},
                   max_calls_per_job=max_calls_per_job, max_calls_per_day=max_calls_per_day, domain=domain,
                   lexicon_path=Path(lexicon) if lexicon else None, examples_dir=Path(examples_dir) if examples_dir else None)


# ----------------------------------------------------------------------------- jobs

@dataclass
class Job:
    job_id: str
    workspace: str
    config: dict
    created: str
    status: str = "queued"
    started: str | None = None
    finished: str | None = None
    progress: dict = field(default_factory=lambda: {"done": 0, "total": 0, "ok": 0, "errors": 0, "eta_s": None})
    error: str | None = None
    headline: dict | None = None
    api_key: str | None = field(default=None, repr=False)
    stop: threading.Event = field(default_factory=threading.Event, repr=False)

    def public(self) -> dict:
        return {"job_id": self.job_id, "workspace": self.workspace, "status": self.status, "created": self.created,
                "started": self.started, "finished": self.finished, "progress": self.progress, "config": self.config,
                "error": self.error, "headline": self.headline}


class Service:
    def __init__(self, cfg: ServiceConfig):
        self.cfg = cfg
        self.root = cfg.root
        (self.root / "jobs").mkdir(parents=True, exist_ok=True)
        (self.root / "uploads").mkdir(parents=True, exist_ok=True)
        (self.root / "lexicons").mkdir(parents=True, exist_ok=True)
        self.lx = None
        if cfg.lexicon_path:
            self.lx = lex_mod.load(cfg.lexicon_path)
        elif cfg.domain:
            from .domains import lexicon_path
            self.lx = lex_mod.load(lexicon_path(cfg.domain))
        self.examples_dir = cfg.examples_dir or (Path(__file__).resolve().parents[1] / "examples")
        self.jobs: dict[str, Job] = {}
        self.lock = threading.Lock()
        self.queue: queue.Queue = queue.Queue()
        self.rate: dict[str, list[float]] = {}
        self._restore_jobs()
        self.threads = [threading.Thread(target=self._worker, daemon=True) for _ in range(max(1, cfg.workers))]
        for t in self.threads:
            t.start()

    # ---- persistence
    def _job_dir(self, job_id: str) -> Path:
        return self.root / "jobs" / job_id

    def _save(self, job: Job) -> None:
        d = self._job_dir(job.job_id)
        d.mkdir(parents=True, exist_ok=True)
        (d / "job.json").write_text(json.dumps(job.public(), indent=1), encoding="utf-8")

    def _restore_jobs(self) -> None:
        for d in sorted((self.root / "jobs").glob("*")):
            f = d / "job.json"
            if not f.exists():
                continue
            try:
                p = json.loads(f.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            job = Job(p["job_id"], p.get("workspace", "public"), p.get("config", {}), p.get("created", _now()), p.get("status", "failed"),
                      p.get("started"), p.get("finished"), p.get("progress") or {}, p.get("error"), p.get("headline"))
            if job.status not in TERMINAL:
                job.status = "interrupted"
                self._save(job)
            self.jobs[job.job_id] = job

    # ---- case sets
    def case_sets(self, workspace: str) -> list[dict]:
        sets = []
        if self.cfg.domain and SAMPLE_CASES is not None:
            sets.append({**self._case_set_entry("sample", f"{self.cfg.domain} sample ({sum(1 for _ in read_jsonl(SAMPLE_CASES))} cases)", SAMPLE_CASES, SAMPLE_PERTS, "packaged"),
                         "domain": self.cfg.domain})
        if self.cfg.extra_cases and self.cfg.extra_cases.exists():
            perts = self.cfg.extra_cases.with_name("perturbations.jsonl")
            sets.append(self._case_set_entry("extra", self.cfg.extra_cases.name, self.cfg.extra_cases, perts if perts.exists() else None, "operator"))
        for d in sorted((self.root / "uploads").glob("*")):
            meta = d / "upload.json"
            if meta.exists():
                m = json.loads(meta.read_text(encoding="utf-8"))
                if m.get("workspace") == workspace:
                    sets.append({"id": m["upload_id"], "name": m.get("name") or m["upload_id"], "n_cases": m["n_cases"],
                                 "n_perturbations": m["n_perturbations"], "approved": m.get("approved", False), "source": "upload",
                                 "lexicon": m.get("lexicon", False), "domain": m.get("domain")})
        return sets

    def _case_set_entry(self, cid: str, name: str, cases: Path, perts: Path | None, source: str) -> dict:
        cs = load_cases(cases)
        n_p = sum(1 for _ in read_jsonl(perts)) if perts and perts.exists() else 0
        return {"id": cid, "name": name, "n_cases": len(cs), "n_perturbations": n_p,
                "approved": all(c.review.status == "approved" for c in cs), "source": source}

    def _resolve_case_set(self, cid: str, workspace: str) -> tuple[Path, Path | None, Path | None, bool]:
        """-> (cases_path, perturbations_path, lexicon_path, approved)"""
        if cid == "sample":
            if not (self.cfg.domain and SAMPLE_CASES is not None):
                raise ApiError(404, "case_set_not_found", "no packaged sample on this server")
            from .domains import lexicon_path
            return SAMPLE_CASES, SAMPLE_PERTS, lexicon_path(self.cfg.domain), True
        if cid == "extra" and self.cfg.extra_cases:
            p = self.cfg.extra_cases.with_name("perturbations.jsonl")
            cs = load_cases(self.cfg.extra_cases)
            return self.cfg.extra_cases, p if p.exists() else None, None, all(c.review.status == "approved" for c in cs)
        d = self.root / "uploads" / cid
        meta = d / "upload.json"
        if not meta.exists():
            raise ApiError(404, "case_set_not_found", f"unknown case set {cid!r}")
        m = json.loads(meta.read_text(encoding="utf-8"))
        if m.get("workspace") != workspace:
            raise ApiError(403, "forbidden", "case set belongs to another workspace")
        perts = d / "perturbations.jsonl"
        lex = d / "lexicon.json"
        return d / "cases.jsonl", perts if perts.exists() else None, lex if lex.exists() else None, bool(m.get("approved"))

    # ---- uploads
    def create_upload(self, workspace: str, body: dict) -> dict:
        cases_text = body.get("cases")
        if not isinstance(cases_text, str) or not cases_text.strip():
            raise ApiError(400, "bad_request", "cases (JSONL text) is required")
        upload_id = "up-" + uuid.uuid4().hex[:10]
        d = self.root / "uploads" / upload_id
        d.mkdir(parents=True)
        lex = None
        if body.get("lexicon"):
            (d / "lexicon.json").write_text(body["lexicon"], encoding="utf-8")
            try:
                lex = lex_mod.load(d / "lexicon.json")
            except (ValueError, json.JSONDecodeError, KeyError) as e:
                shutil.rmtree(d, ignore_errors=True)
                raise ApiError(400, "bad_lexicon", f"lexicon rejected: {e}")
        elif body.get("lexicon_id"):
            try:
                lex = self.lexicon_for(body["lexicon_id"], workspace)
            except ApiError:
                shutil.rmtree(d, ignore_errors=True)
                raise
            shutil.copy(lex.path, d / "lexicon.json")
        else:
            lex = self.lx
        if lex is None:
            shutil.rmtree(d, ignore_errors=True)
            raise ApiError(400, "lexicon_required", "choose a lexicon_id or include a lexicon with the cases")
        try:
            cases = [Case.from_dict(json.loads(line)) for line in cases_text.splitlines() if line.strip()]
        except (json.JSONDecodeError, TypeError, KeyError, ValueError) as e:
            shutil.rmtree(d, ignore_errors=True)
            raise ApiError(400, "bad_cases", f"cases rejected: {e}")
        problems = []
        approved = bool(body.get("approved"))
        for c in cases:
            if approved:
                c.review = Review(reviewer_id=body.get("reviewer_id") or "uploader", date=_now()[:10], status="approved", notes="approved on upload")
            problems += [str(p) for p in validate_case(c, lex) if p.severity == "error"]
        if problems:
            shutil.rmtree(d, ignore_errors=True)
            raise ApiError(400, "invalid_cases", "; ".join(problems[:20]) + (f" (+{len(problems) - 20} more)" if len(problems) > 20 else ""))
        perts = []
        if body.get("perturbations"):
            try:
                from .schema import Perturbation
                perts = [Perturbation.from_dict(json.loads(line)) for line in body["perturbations"].splitlines() if line.strip()]
            except (json.JSONDecodeError, TypeError, KeyError, ValueError) as e:
                shutil.rmtree(d, ignore_errors=True)
                raise ApiError(400, "bad_perturbations", f"perturbations rejected: {e}")
            by = {c.case_id: c for c in cases}
            for p in perts:
                if approved:
                    p.review = Review(reviewer_id=body.get("reviewer_id") or "uploader", date=_now()[:10], status="approved", notes="approved on upload")
                problems += [str(x) for x in validate_perturbation(p, by.get(p.case_id), lex) if x.severity == "error"]
        elif body.get("generate_perturbations", True):
            for c in cases:
                try:
                    perts += perturb.generate_all(c, int(body.get("seed", 20261020)), lex, include_right=True)
                except perturb.PerturbationError as e:
                    problems.append(f"{c.case_id}: could not generate perturbations: {e}")
            if approved:
                for p in perts:
                    p.review = Review(reviewer_id="generator", date=_now()[:10], status="approved", notes="generated on upload")
        if problems:
            shutil.rmtree(d, ignore_errors=True)
            raise ApiError(400, "invalid_cases", "; ".join(problems[:20]) + (f" (+{len(problems) - 20} more)" if len(problems) > 20 else ""))
        write_jsonl(d / "cases.jsonl", cases)
        if perts:
            write_jsonl(d / "perturbations.jsonl", perts)
        meta = {"upload_id": upload_id, "workspace": workspace, "name": body.get("name") or upload_id, "created": _now(),
                "n_cases": len(cases), "n_perturbations": len(perts), "approved": approved, "lexicon": (d / "lexicon.json").exists(),
                "domain": lex.domain}
        (d / "upload.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
        return {**meta, "problems": []}

    # ---- lexicons
    def lexicons(self, workspace: str) -> list[dict]:
        out = []
        if self.lx is not None:
            out.append({"id": "default", "name": self.lx.domain, "domain": self.lx.domain, "version": self.lx.version, "sections": self.lx.sections,
                        "n_findings": len(self.lx.findings), "n_entities": len(self.lx.in_scope_entities()), "source": "packaged"})
        for path in sorted(self.examples_dir.glob("lexicon-*.json")) if self.examples_dir and self.examples_dir.exists() else []:
            try:
                lx = lex_mod.load(path)
            except Exception:  # noqa: BLE001 - skip broken examples
                continue
            name = path.stem[len("lexicon-"):]
            out.append({"id": f"example:{name}", "name": name.replace("-", " "), "domain": lx.domain, "version": lx.version, "sections": lx.sections,
                        "n_findings": len(lx.findings), "n_entities": len(lx.in_scope_entities()), "source": "example"})
        for d in sorted((self.root / "lexicons").glob("*")):
            meta = d / "lexicon.meta.json"
            if meta.exists():
                m = json.loads(meta.read_text(encoding="utf-8"))
                if m.get("workspace") in (workspace, "public"):
                    out.append({k: m[k] for k in ("id", "domain", "version", "sections", "n_findings", "n_entities", "source", "name")})
        return out

    def create_lexicon(self, workspace: str, body: dict) -> dict:
        text = body.get("lexicon")
        if not isinstance(text, str) or not text.strip():
            raise ApiError(400, "bad_request", "lexicon (JSON text) is required")
        lid = "lex-" + uuid.uuid4().hex[:10]
        d = self.root / "lexicons" / lid
        d.mkdir(parents=True)
        (d / "lexicon.json").write_text(text, encoding="utf-8")
        try:
            lx = lex_mod.load(d / "lexicon.json")
        except (ValueError, json.JSONDecodeError, KeyError, TypeError) as e:
            shutil.rmtree(d, ignore_errors=True)
            raise ApiError(400, "bad_lexicon", f"lexicon rejected: {e}")
        meta = {"id": lid, "workspace": workspace, "name": body.get("name") or lx.domain, "domain": lx.domain, "version": lx.version,
                "sections": lx.sections, "n_findings": len(lx.findings), "n_entities": len(lx.in_scope_entities()), "source": "upload", "created": _now()}
        (d / "lexicon.meta.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
        return meta

    def lexicon_for(self, lexicon_id: str | None, workspace: str):
        if not lexicon_id or lexicon_id == "default":
            if self.lx is None:
                raise ApiError(400, "lexicon_required", "choose a lexicon (lexicon_id): this server has no built-in domain")
            return self.lx
        if lexicon_id.startswith("example:"):
            path = (self.examples_dir or Path(".")) / f"lexicon-{lexicon_id[len('example:'):]}.json"
            if not path.exists():
                raise ApiError(404, "lexicon_not_found", f"unknown example lexicon {lexicon_id!r}")
            return lex_mod.load(path)
        d = self.root / "lexicons" / lexicon_id
        meta = d / "lexicon.meta.json"
        if not meta.exists():
            raise ApiError(404, "lexicon_not_found", f"unknown lexicon {lexicon_id!r}")
        m = json.loads(meta.read_text(encoding="utf-8"))
        if m.get("workspace") not in (workspace, "public"):
            raise ApiError(403, "forbidden", "lexicon belongs to another workspace")
        return lex_mod.load(d / "lexicon.json")

    # ---- fact ledger (structured traces with citations)
    def ledger_audit(self, body: dict) -> dict:
        from .importers import parse_markdown
        if isinstance(body.get("markdown"), str) and body["markdown"].strip():
            if len(body["markdown"]) > 2_000_000:
                raise ApiError(400, "too_large", "markdown exceeds 2 MB")
            case, trace = parse_markdown(body["markdown"])
        elif isinstance(body.get("case"), dict) and isinstance(body.get("trace"), dict):
            try:
                case, trace = ledger_from_json(body["case"], body["trace"])
            except (KeyError, TypeError, ValueError) as e:
                raise ApiError(400, "bad_request", f"ledger JSON rejected: {e}")
        else:
            raise ApiError(400, "bad_request", "send {markdown: <ENABLE trace artefact>} or {case: {...}, trace: {...}}")
        if not case.facts:
            raise ApiError(400, "bad_request", "no facts found in the input")
        return ledger_mod.audit(case, trace, self.lx)

    # ---- analyse
    def analyse(self, body: dict, workspace: str = "public") -> dict:
        lx = self.lexicon_for(body.get("lexicon_id"), workspace)
        # `documents` is the general form ({section id: text}, any domain); `reports` is the haematology shorthand
        documents = body.get("documents")
        sections: list[dict] | None = None
        if isinstance(documents, dict) and documents:
            titles = body.get("titles") or {}
            known = {sec["id"]: sec.get("title") for sec in lx.sections}
            sections = [{"id": k, "title": titles.get(k) or known.get(k) or k.replace("_", " ").capitalize()} for k in documents]
            reports = {k: v for k, v in documents.items()}
            keys = list(documents)
        else:
            reports = body.get("reports") or {}
            keys = [sec["id"] for sec in lx.sections]
            sections = list(lx.sections)
        if not isinstance(reports, dict) or not any((reports.get(k) or "").strip() for k in keys):
            raise ApiError(400, "bad_request", "documents must contain at least one of " + ", ".join(keys))
        if len(keys) > 20:
            raise ApiError(400, "bad_request", "at most 20 documents")
        for k in keys:
            v = reports.get(k) or ""
            if not isinstance(v, str):
                raise ApiError(400, "bad_request", f"document {k} must be a string")
            if len(v) > MAX_REPORT_CHARS:
                raise ApiError(400, "too_large", f"document {k} exceeds {MAX_REPORT_CHARS} characters")
        reasoning = body.get("reasoning") or ""
        answer = body.get("answer") or ""
        if not isinstance(reasoning, str) or not isinstance(answer, str):
            raise ApiError(400, "bad_request", "reasoning and answer must be strings")
        if len(reasoning) > MAX_REASONING_CHARS:
            raise ApiError(400, "too_large", f"reasoning exceeds {MAX_REASONING_CHARS} characters")
        entity = body.get("entity") or None
        if entity is not None and entity not in lx.entities:
            raise ApiError(400, "bad_request", f"entity {entity!r} is not in the lexicon")
        case = Case(case_id="ANL-001", entity=entity or "UNKNOWN", reports={k: reports.get(k) or "" for k in keys}, truth={}, sections=sections)
        truth = body.get("truth")
        oracle = "truth"
        warnings: list[str] = []
        if not isinstance(truth, dict) or not truth:
            oracle = "extracted"
            truth = {}
            for a in extract.extract_assertions(case.render(), lx):
                if a.polarity and a.finding_id not in truth:
                    truth[a.finding_id] = a.polarity
                elif a.polarity and truth[a.finding_id] != a.polarity:
                    warnings.append(f"conflicting polarity for {a.finding_id} in the reports; first occurrence used")
        case.truth = truth
        trace = Trace("ANL-001|base|medium|0", "ANL-001", "base", "medium", 0, body.get("model") or "submitted", reasoning, answer)
        claims = segment.segment(reasoning, trace.trace_key, lx)
        # the text path is an adapter onto the fact ledger: documents -> facts, factual claims -> cited segments
        case_ledger = ledger_adapters.case_to_ledger(case, lx, truth_overrides=(oracle == "truth"))
        trace_ledger = ledger_adapters.trace_to_ledger(trace, claims, lx, case_ledger)
        result = ledger_mod.audit(case_ledger, trace_ledger, lx)
        spans = case_ledger.meta.get("spans", {})
        documents = [{"id": k, "title": t, "text": case.reports.get(k) or "",
                      "facts": [{"id": fid, "start": sp["start"], "end": sp["end"]} for fid, sp in spans.items() if sp["report"] == k]}
                     for k, t in case.section_list()]
        result.update({
            "documents": documents,
            "lexicon": {"id": body.get("lexicon_id") or "default", "domain": lx.domain, "version": lx.version,
                        "entities": [{"id": e["id"], "display": e["display"]} for e in lx.data["entities"]],
                        "findings": [{"id": f["id"], "display": f["display"], "kind": f["kind"]} for f in lx.data["findings"]]},
            "answer": {"text": answer, "entity": trace_ledger.report.decision, "entity_raw": trace_ledger.meta.get("entity_raw"),
                       "subtype": trace_ledger.meta.get("subtype"), "hedged": trace_ledger.meta.get("hedged"),
                       "entities_named": trace_ledger.meta.get("entities_named"), "claims": trace_ledger.meta.get("claims"),
                       "factual_claims": trace_ledger.meta.get("factual_claims")},
            "oracle": oracle, "warnings": sorted(set(warnings)), "lexicon_version": lx.version, "domain": lx.domain,
        })
        return result

    # ---- jobs
    def submit(self, workspace: str, body: dict) -> Job:
        if body.get("mode", "audit") != "audit":
            raise ApiError(400, "bad_request", "mode must be 'audit'")
        client = body.get("client") or {}
        kind = client.get("kind")
        if kind not in self.cfg.allow_clients:
            raise ApiError(403, "client_not_allowed", f"client kind {kind!r} is not enabled on this server (allowed: {sorted(self.cfg.allow_clients)})")
        model = client.get("model") or ("simulated" if kind == "sim" else None)
        if not model:
            raise ApiError(400, "bad_request", "client.model is required")
        efforts = body.get("efforts") or list(EFFORTS)
        if not isinstance(efforts, list) or any(e not in EFFORTS for e in efforts):
            raise ApiError(400, "bad_request", "efforts must be a list of low, medium, high")
        runs = int(body.get("runs", 3))
        if not 1 <= runs <= 10:
            raise ApiError(400, "bad_request", "runs must be between 1 and 10")
        case_set = body.get("case_set") or "sample"
        cases_path, perts_path, lex_path, approved = self._resolve_case_set(case_set, workspace)
        if not approved:
            raise ApiError(409, "case_set_unapproved", "this case set has not been approved for runs")
        api_key = client.get("api_key") or None
        key_source = "user"
        if kind != "sim" and not api_key:
            if kind in self.cfg.operator_keys:
                api_key = self.cfg.operator_keys[kind]
                key_source = "operator"
            else:
                raise ApiError(403, "key_required", f"an API key for {kind} is required on this server")
        # spend caps: the exact number of planned calls (honours the variant filter)
        lx_for_plan = lex_mod.load(lex_path) if lex_path else self.lx
        if lx_for_plan is None:
            raise ApiError(400, "lexicon_required", "this case set has no lexicon and the server has no built-in domain")
        est_calls = len(experiment.plan(load_cases(cases_path), load_perturbations(perts_path) if perts_path else [], efforts, runs,
                                        int(body.get("seed", 20261020)), variant_filter=body.get("variants"), lexicon=lx_for_plan))
        if est_calls == 0:
            raise ApiError(400, "bad_request", "no calls would be made (case set empty, unapproved, or filtered out)")
        if kind != "sim":
            if est_calls > self.cfg.max_calls_per_job:
                raise ApiError(400, "job_too_large", f"this job would make about {est_calls} model calls; the limit per job is {self.cfg.max_calls_per_job}")
            if key_source == "operator" and self._calls_today() + est_calls > self.cfg.max_calls_per_day:
                raise ApiError(429, "budget_exhausted", "the site's daily budget for model calls is used up; try again tomorrow or supply your own key")
        job_id = "job-" + uuid.uuid4().hex[:10]
        config = {"mode": "audit", "client": {"kind": kind, "endpoint": client.get("endpoint"), "model": model},
                  "case_set": case_set, "efforts": efforts, "runs": runs, "variants": body.get("variants"), "seed": int(body.get("seed", 20261020)),
                  "rule": body.get("rule", "D1"), "judge": bool(body.get("judge", False)), "notes": (body.get("notes") or "")[:2000],
                  "sim_p": body.get("sim_p"), "key_source": key_source, "estimated_calls": est_calls,
                  "paths": {"cases": str(cases_path), "perturbations": str(perts_path) if perts_path else None,
                            "lexicon": str(lex_path) if lex_path else None}}
        job = Job(job_id, workspace, config, _now(), api_key=api_key)
        with self.lock:
            self.jobs[job_id] = job
            self._save(job)
        self.queue.put(job_id)
        return job

    def _calls_today(self) -> int:
        today = _now()[:10]
        return sum(int(j.config.get("estimated_calls") or 0) for j in self.jobs.values()
                   if j.config.get("key_source") == "operator" and j.status not in ("failed", "cancelled") and (j.created or "")[:10] == today)

    def limits(self) -> dict:
        return {"max_calls_per_job": self.cfg.max_calls_per_job, "max_calls_per_day": self.cfg.max_calls_per_day,
                "calls_used_today": self._calls_today(), "operator_keys": sorted(self.cfg.operator_keys)}

    def cancel(self, job: Job) -> None:
        if job.status in TERMINAL:
            raise ApiError(409, "not_running", f"job is {job.status}")
        job.stop.set()
        if job.status == "queued":
            job.status = "cancelled"
            job.finished = _now()
            self._save(job)

    def resume(self, job: Job, api_key: str | None) -> None:
        if job.status not in ("interrupted", "failed", "cancelled"):
            raise ApiError(409, "not_resumable", f"job is {job.status}")
        kind = job.config.get("client", {}).get("kind")
        if not api_key and kind in self.cfg.operator_keys:
            api_key = self.cfg.operator_keys[kind]
        job.api_key = api_key
        job.stop = threading.Event()
        job.status = "queued"
        job.error = None
        self._save(job)
        self.queue.put(job.job_id)

    def _worker(self) -> None:
        while True:
            job_id = self.queue.get()
            job = self.jobs.get(job_id)
            if job is None or job.status != "queued":
                continue
            try:
                self._run_job(job)
            except Exception as e:  # noqa: BLE001
                job.status = "failed"
                job.error = f"{type(e).__name__}: {e}"
                job.finished = _now()
                job.extra_tb = traceback.format_exc()  # type: ignore[attr-defined]
            finally:
                job.api_key = None
                self._save(job)

    def _run_job(self, job: Job) -> None:
        cfg = job.config
        d = self._job_dir(job.job_id)
        run_dir = d / "run"
        lx = lex_mod.load(cfg["paths"]["lexicon"]) if cfg["paths"].get("lexicon") else self.lx
        if lx is None:
            raise RuntimeError("no lexicon for this job")
        cases = load_cases(cfg["paths"]["cases"])
        perts = load_perturbations(cfg["paths"]["perturbations"]) if cfg["paths"].get("perturbations") else []
        ckind = cfg["client"]["kind"]
        kw: dict[str, Any] = {}
        if ckind == "sim":
            from .simulate import SimParams
            p = cfg.get("sim_p")
            kw = {"params": SimParams.uniform(float(p), p_base_noise=0.0, p_trace_answer_mismatch=0.0) if p is not None else SimParams(), "seed": cfg["seed"]}
        elif job.api_key:
            kw = {"api_key": job.api_key}
        client = make_client(ckind, cfg["client"]["model"], cfg["client"].get("endpoint"), **kw)
        prompt = experiment.load_prompt("enable-v3")
        jobs = experiment.plan(cases, perts, cfg["efforts"], cfg["runs"], cfg["seed"], variant_filter=cfg.get("variants"), lexicon=lx)
        if not jobs:
            raise RuntimeError("no jobs planned (case set empty or filtered out)")
        job.status = "running"
        job.started = _now()
        job.progress = {"done": 0, "total": len(jobs), "ok": 0, "errors": 0, "eta_s": None}
        self._save(job)
        if (run_dir / "manifest.json").exists():
            manifest = experiment.read_manifest(run_dir)
            manifest["status"] = "running"
        else:
            manifest = experiment.build_manifest(experiment.new_run_id(random.Random(cfg["seed"])), client, prompt, cfg["efforts"], cfg["runs"], cfg["seed"],
                                                 cfg["paths"]["cases"], cfg["paths"]["perturbations"], lx, len(cases), len(perts),
                                                 {"variants": cfg.get("variants"), "workspace": job.workspace}, {}, 1,
                                                 f"service job {job.job_id}; {cfg.get('notes', '')}", "service run")
        last_save = [0.0]

        def progress(msg: str) -> None:
            try:
                pj = json.loads((run_dir / "progress.json").read_text())
                job.progress = {"done": pj.get("done", 0), "total": pj.get("total", len(jobs)), "ok": pj.get("ok", 0),
                                "errors": pj.get("errors", 0), "eta_s": pj.get("eta_s")}
            except (OSError, json.JSONDecodeError):
                pass
            if time.time() - last_save[0] > 2:
                last_save[0] = time.time()
                self._save(job)

        counts = experiment.run_experiment(jobs, client, run_dir, manifest, prompt, cfg["seed"], progress=progress, should_stop=job.stop.is_set)
        job.progress = {"done": counts.get("done", 0), "total": counts.get("total", len(jobs)), "ok": counts.get("ok", 0), "errors": counts.get("errors", 0), "eta_s": 0}
        if counts.get("cancelled"):
            job.status = "cancelled"
        if not (run_dir / "traces.jsonl").exists():
            job.finished = _now()
            return
        job.status = "scoring" if job.status != "cancelled" else job.status
        self._save(job)
        case_entities = {c.case_id: c.entity for c in cases}
        pipeline.score_all(run_dir, cases, perts, cfg.get("rule", "D1"), "lexical", 500, cfg["seed"], lx)
        if cfg.get("judge"):
            pass  # judge requires a judge client; not exposed in v1 of the service
        from .report import render_markdown
        (run_dir / "report.md").write_text(render_markdown(json.loads((run_dir / "summary.json").read_text())), encoding="utf-8")
        if job.status != "cancelled":
            job.status = "exporting"
        self._save(job)
        export.to_viewer(run_dir, d / "export", cases, perts, shard=True, lexicon=lx, redact_prompt=False)
        s = json.loads((run_dir / "summary.json").read_text())
        job.headline = {
            "traces": s["counts"]["traces"], "errors": s["counts"]["errors"],
            "grounding_rate": s["grounding"]["pooled_rate"]["point"],
            "silent_rate": s["counterfactual"]["decisive"]["silent_rate"]["point"],
            "spurious_rate": s["counterfactual"]["neutral"]["spurious_rate"]["point"],
            "silent_shift_rate": s["authority"]["wrong"]["silent_shift_rate"]["point"],
        }
        del case_entities
        if job.status != "cancelled":
            job.status = "done"
        job.finished = _now()

    # ---- rate limiting
    def check_rate(self, addr: str) -> None:
        now = time.time()
        with self.lock:
            hits = [t for t in self.rate.get(addr, []) if now - t < 60]
            if len(hits) >= self.cfg.rate_per_min:
                raise ApiError(429, "rate_limited", "too many requests; try again in a minute")
            hits.append(now)
            self.rate[addr] = hits


def ledger_from_json(case_d: dict, trace_d: dict):
    """Build ledger records from plain JSON (the shape `ledger.audit` returns under case/trace, minus derived fields)."""
    from . import ledger as L
    facts = [L.Fact(f["id"], f.get("source", "patient"), f.get("section", ""), f.get("field", ""), str(f.get("value", "")), f.get("evidence", ""), f.get("candidate"))
             for f in case_d.get("facts", [])]
    case = L.LedgerCase(case_d.get("case_id", "case"), case_d.get("truth"), list(case_d.get("candidates", [])), facts,
                        set(case_d.get("allowed_ids", [])) | {f.id for f in facts}, case_d.get("meta", {}))
    rep = trace_d.get("report") or {}
    report = L.Report(rep.get("decision"), [L.Section(sec.get("title", ""), [L.Segment(sg.get("text", ""), list(sg.get("citation_ids", [])))
                                                                              for sg in sec.get("segments", [])]) for sec in rep.get("sections", [])],
                      rep.get("delivered_decision"), rep.get("contract_valid"), rep.get("failure_kind"), rep.get("dropped_segments", []))
    rationale = None
    if trace_d.get("rationale"):
        r = trace_d["rationale"]
        rationale = L.Rationale(r.get("decision"), r.get("confidence"), r.get("key_findings", []),
                                [L.DifferentialEntry(d["diagnosis"], d.get("verdict", "unknown"), d.get("supporting", []), d.get("contradicting", []), d.get("rationale", ""),
                                                     [L.Criterion(c["criterion"], c.get("status", "not_assessable"), c.get("ids", [])) for c in d.get("criteria", [])])
                                 for d in r.get("differential", [])],
                                r.get("discriminators", []), r.get("unresolved", []), r.get("would_change", []), r.get("thinking", ""))
    ablation = None
    if trace_d.get("ablation"):
        a = trace_d["ablation"]
        ablation = L.Ablation(list(a.get("removed_ids", [])), a.get("decision_before"), a.get("decision_after"), a.get("changed"))
    return case, L.LedgerTrace(trace_d.get("thinking", ""), report, rationale, ablation, trace_d.get("meta", {}))


# ----------------------------------------------------------------------------- HTTP

class Handler(BaseHTTPRequestHandler):
    service: Service  # set by make_server
    server_version = f"traceaudit/{__version__}"

    def log_message(self, fmt, *args):  # quieter default log
        if os.environ.get("TRACEAUDIT_HTTP_LOG"):
            super().log_message(fmt, *args)

    # ---- helpers
    def _json(self, status: int, payload: Any, headers: dict | None = None) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def _error(self, e: ApiError) -> None:
        self._json(e.status, {"error": {"code": e.code, "message": e.message}})

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        if n > 20 * 1024 * 1024:
            raise ApiError(413, "too_large", "request body too large")
        raw = self.rfile.read(n) if n else b""
        if not raw:
            return {}
        try:
            d = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            raise ApiError(400, "bad_json", f"invalid JSON body: {e}")
        if not isinstance(d, dict):
            raise ApiError(400, "bad_json", "body must be a JSON object")
        return d

    def _workspace(self) -> tuple[str, bool]:
        auth = self.headers.get("Authorization") or ""
        if auth.lower().startswith("bearer "):
            token = auth[7:].strip()
            ws = self.service.cfg.tokens.get(token)
            if ws is None:
                raise ApiError(401, "bad_token", "unknown token")
            return ws, True
        return "public", False

    def _require(self, action: str) -> str:
        ws, authed = self._workspace()
        if authed:
            return ws
        mode = self.service.cfg.anonymous
        if mode == "all" or (mode == "analyse" and action == "analyse") or action == "read":
            if action == "analyse":
                self.service.check_rate(self.client_address[0])
            return ws
        raise ApiError(401, "auth_required", "this action needs a bearer token")

    def _job(self, job_id: str, ws: str) -> Job:
        job = self.service.jobs.get(job_id)
        if job is None or (job.workspace != ws and ws != "admin"):
            raise ApiError(404, "job_not_found", f"unknown job {job_id!r}")
        return job

    def _send_file(self, path: Path, download: bool = False) -> None:
        if not path.exists() or not path.is_file():
            raise ApiError(404, "not_found", "file not found")
        ctype = mimetypes.guess_type(str(path))[0] or ("application/json" if path.suffix == ".jsonl" else "application/octet-stream")
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        if path.suffix in (".html", ".json", ".jsonl", ".md", ".csv"):
            self.send_header("Cache-Control", "no-cache")  # hashed assets may be cached; entry points and data must not be
        if download:
            self.send_header("Content-Disposition", f'attachment; filename="{path.name}"')
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    # ---- routing
    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", self.headers.get("Origin") or "*")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.end_headers()

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        try:
            self._route("GET")
        except ApiError as e:
            self._error(e)

    def do_POST(self):
        try:
            self._route("POST")
        except ApiError as e:
            self._error(e)

    def do_DELETE(self):
        try:
            self._route("DELETE")
        except ApiError as e:
            self._error(e)

    def _route(self, method: str) -> None:
        url = urlparse(self.path)
        path = unquote(url.path)
        svc = self.service
        if path.startswith("/api/"):
            try:
                self._api(method, path, parse_qs(url.query))
            except ApiError:
                raise
            except Exception as e:  # noqa: BLE001
                traceback.print_exc()
                raise ApiError(500, "internal", f"{type(e).__name__}: {e}")
            return
        if method != "GET":
            raise ApiError(405, "method_not_allowed", "only GET for static files")
        static = svc.cfg.static
        if static is None:
            self._json(200, {"service": "traceaudit", "version": __version__, "viewer": None, "api": "/api/health"})
            return
        rel = path.lstrip("/") or "index.html"
        target = (static / rel).resolve()
        if not str(target).startswith(str(static.resolve())):
            raise ApiError(403, "forbidden", "path outside static root")
        if target.is_dir():
            target = target / "index.html"
        if not target.exists():
            target = static / "index.html"  # SPA fallback
        self._send_file(target)

    def _api(self, method: str, path: str, query: dict) -> None:
        svc = self.service
        parts = [p for p in path.split("/") if p][1:]  # drop 'api'
        if method == "GET" and parts == ["health"]:
            ws, _ = self._workspace()
            self._json(200, {"version": __version__, "lexicon_version": svc.lx.version if svc.lx else None, "modes": ["analyse", "audit"],
                             "clients": sorted(svc.cfg.allow_clients), "anonymous": svc.cfg.anonymous, "workspace": ws,
                             "viewer": svc.cfg.static is not None, "operator_keys": sorted(svc.cfg.operator_keys), "limits": svc.limits(),
                             "domain": svc.lx.domain if svc.lx else None, "sections": svc.lx.sections if svc.lx else []})
            return
        if method == "GET" and parts == ["lexicon"]:
            ws, _ = self._workspace()
            lx = svc.lexicon_for((query.get("id") or ["default"])[0], ws)
            self._json(200, {"version": lx.version, "domain": lx.domain, "sections": lx.sections,
                             "entities": [{"id": e["id"], "display": e["display"], "in_scope": e["in_scope"], "parent": e.get("parent")} for e in lx.data["entities"]],
                             "findings": [{"id": f["id"], "display": f["display"], "kind": f["kind"]} for f in lx.data["findings"]]})
            return
        if method == "GET" and parts == ["case-sets"]:
            ws = self._require("read")
            self._json(200, svc.case_sets(ws))
            return
        if method == "POST" and parts == ["analyse"]:
            ws = self._require("analyse")
            self._json(200, svc.analyse(self._body(), ws))
            return
        if method == "POST" and parts == ["ledger"]:
            self._require("analyse")
            self._json(200, svc.ledger_audit(self._body()))
            return
        if method == "GET" and parts == ["lexicons"]:
            ws = self._require("read")
            self._json(200, svc.lexicons(ws))
            return
        if method == "POST" and parts == ["lexicons"]:
            ws = self._require("analyse")
            self._json(201, svc.create_lexicon(ws, self._body()))
            return
        if method == "POST" and parts == ["uploads"]:
            ws = self._require("job")
            self._json(201, svc.create_upload(ws, self._body()))
            return
        if parts and parts[0] == "jobs":
            if method == "POST" and len(parts) == 1:
                ws = self._require("job")
                job = svc.submit(ws, self._body())
                self._json(202, {"job_id": job.job_id, "status": job.status})
                return
            if method == "GET" and len(parts) == 1:
                ws = self._require("read")
                jobs = [j.public() for j in svc.jobs.values() if j.workspace == ws]
                jobs.sort(key=lambda j: j["created"], reverse=True)
                self._json(200, jobs)
                return
            ws = self._require("read")
            job = self._job(parts[1], ws)
            if method == "GET" and len(parts) == 2:
                self._json(200, job.public())
                return
            if method == "DELETE" and len(parts) == 2:
                self._require("job")
                svc.cancel(job)
                self._json(200, job.public())
                return
            if method == "POST" and len(parts) == 3 and parts[2] == "resume":
                self._require("job")
                body = self._body()
                svc.resume(job, (body.get("client") or {}).get("api_key"))
                self._json(202, job.public())
                return
            if method == "GET" and len(parts) >= 3 and parts[2] == "bundle":
                rel = "/".join(parts[3:]) or "index.json"
                base = (svc.root / "jobs" / job.job_id / "export").resolve()
                target = (base / rel).resolve()
                if not str(target).startswith(str(base)):
                    raise ApiError(403, "forbidden", "path outside bundle")
                self._send_file(target)
                return
            if method == "GET" and len(parts) == 4 and parts[2] == "files":
                name = parts[3]
                if not re.fullmatch(r"(summary\.json|report\.md|traces\.jsonl|long\.csv|manifest\.json|claims\.jsonl|grounding\.jsonl|counterfactual\.jsonl|authority\.jsonl)", name):
                    raise ApiError(404, "not_found", "unknown file")
                self._send_file(svc.root / "jobs" / job.job_id / "run" / name, download=True)
                return
        raise ApiError(404, "not_found", f"no route for {method} {path}")


def make_server(cfg: ServiceConfig) -> ThreadingHTTPServer:
    service = Service(cfg)

    class BoundHandler(Handler):
        pass

    BoundHandler.service = service
    httpd = ThreadingHTTPServer((cfg.host, cfg.port), BoundHandler)
    httpd.service = service  # type: ignore[attr-defined]
    return httpd


def serve_forever(cfg: ServiceConfig) -> None:
    httpd = make_server(cfg)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
