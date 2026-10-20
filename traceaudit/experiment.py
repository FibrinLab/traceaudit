"""Run orchestration, manifest and resumption (spec 08)."""
from __future__ import annotations

import datetime as _dt
import json
import platform
import queue
import random
import subprocess
import threading
import time
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

from . import __version__
from . import lexicon as lex_mod
from . import perturb
from .clients.base import ClientError, GenerateRequest, ModelClient
from .lexicon import Lexicon
from .schema import (EFFORTS, Case, Perturbation, Retrieved, Trace, TraceMeta, make_trace_key, read_jsonl, write_jsonl)
from .textutil import sha256_file, sha256_text

PROMPTS_DIR = Path(__file__).with_name("prompts")


@dataclass
class Job:
    case_id: str
    variant: str
    effort: str
    run: int
    rendered: str
    truth_after: dict[str, str]
    meta: dict

    @property
    def trace_key(self) -> str:
        return make_trace_key(self.case_id, self.variant, self.effort, self.run)


def load_prompt(prompt_id: str) -> dict:
    p = PROMPTS_DIR / f"{prompt_id}.json"
    if not p.exists():
        p = Path(prompt_id)
    with open(p, encoding="utf-8") as f:
        d = json.load(f)
    d.setdefault("id", prompt_id)
    d["sha256"] = sha256_text(d["system"] + "\n" + d["user_template"])
    return d


def per_trace_seed(master_seed: int, trace_key: str) -> int:
    return zlib.crc32(f"{master_seed}:{trace_key}".encode()) & 0x7FFFFFFF


def _glob_match(value: str, patterns: list[str] | None) -> bool:
    import fnmatch
    if not patterns:
        return True
    return any(fnmatch.fnmatch(value, p) for p in patterns)


def plan(cases: list[Case], perturbations: list[Perturbation], efforts: Iterable[str] = EFFORTS, runs_per_variant: int = 5,
         master_seed: int = 0, case_filter: list[str] | None = None, entity_filter: list[str] | None = None,
         variant_filter: list[str] | None = None, allow_unreviewed: bool = False, lexicon: Lexicon | None = None,
         right_cue_fraction: float = 0.5) -> list[Job]:
    lx = lexicon or lex_mod.load()
    jobs: list[Job] = []
    rng_right = random.Random(f"{master_seed}:auth-right")
    for c in cases:
        if not allow_unreviewed and c.review.status != "approved":
            continue
        if case_filter and c.case_id not in case_filter:
            continue
        if entity_filter and c.entity not in entity_filter:
            continue
        variants: list[tuple[str, str, dict, dict]] = []
        if _glob_match("base", variant_filter):
            variants.append(("base", c.render(), dict(c.truth), {"kind": "base", "base_entity": c.entity}))
        for p in perturbations:
            if p.case_id != c.case_id:
                continue
            if not allow_unreviewed and p.review.status != "approved":
                continue
            if not _glob_match(p.variant, variant_filter):
                continue
            if p.variant == "auth-right" and rng_right.random() >= right_cue_fraction:
                continue
            v = perturb.apply(c, p, lx, verify=False)
            meta = {"kind": p.kind, "base_entity": c.entity, "primary_finding": p.primary_finding, "co_edits": p.co_edits,
                    "linked_findings": p.linked_findings, "expected_entity": p.expected_entity}
            variants.append((p.variant, v.render(), dict(p.truth_after), meta))
        for variant, rendered, truth_after, meta in variants:
            for eff in efforts:
                for r in range(runs_per_variant):
                    jobs.append(Job(c.case_id, variant, eff, r, rendered, truth_after, meta))
    random.Random(master_seed).shuffle(jobs)  # [PRE-REG] interleaving
    return jobs


def _git_info(repo: Path) -> tuple[str | None, bool | None]:
    try:
        commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=repo, capture_output=True, text=True, timeout=5)
        if commit.returncode != 0:
            return None, None
        dirty = subprocess.run(["git", "status", "--porcelain"], cwd=repo, capture_output=True, text=True, timeout=5)
        return commit.stdout.strip(), bool(dirty.stdout.strip())
    except (OSError, subprocess.SubprocessError):
        return None, None


def new_run_id(rng: random.Random | None = None) -> str:
    rng = rng or random.Random()
    ts = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    suffix = "".join(rng.choice("abcdefghijklmnopqrstuvwxyz0123456789") for _ in range(6))
    return f"{ts}-{suffix}"


def build_manifest(run_id: str, client: ModelClient, prompt: dict, efforts: list[str], runs_per_variant: int, master_seed: int,
                   cases_path: str | Path | None, perturbations_path: str | Path | None, lexicon: Lexicon, n_cases: int, n_perts: int,
                   filters: dict, sampling: dict, workers: int, notes: str = "", allow_dirty: str | None = None) -> dict:
    commit, dirty = _git_info(Path(__file__).resolve().parents[1])
    return {
        "schema_version": 1, "run_id": run_id, "created": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        "status": "running", "traceaudit_version": __version__, "git_commit": commit, "git_dirty": dirty, "allow_dirty": allow_dirty,
        "python": platform.python_version(), "platform": platform.platform(),
        "model": client.describe(),
        "prompt": {"id": prompt["id"], "sha256": prompt["sha256"], "system": prompt["system"], "user_template": prompt["user_template"]},
        "sampling": {"temperature": sampling.get("temperature", 1.0), "top_p": sampling.get("top_p", 1.0), "max_tokens": sampling.get("max_tokens", 8192),
                     "efforts": list(efforts), "runs_per_variant": runs_per_variant, "workers": workers},
        "seeds": {"master": master_seed, "per_trace_rule": "crc32(master_seed:trace_key) & 0x7fffffff"},
        "inputs": {
            "cases": {"path": str(cases_path) if cases_path else None, "sha256": sha256_file(cases_path) if cases_path else None, "n": n_cases},
            "perturbations": {"path": str(perturbations_path) if perturbations_path else None,
                              "sha256": sha256_file(perturbations_path) if perturbations_path else None, "n": n_perts},
            "lexicon": {"path": str(lexicon.path), "version": lexicon.version, "sha256": lexicon.sha256()},
        },
        "filters": filters, "notes": notes, "scoring": [],
    }


def write_manifest(run_dir: Path, manifest: dict) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    tmp = run_dir / "manifest.json.tmp"
    tmp.write_text(json.dumps(manifest, indent=1, ensure_ascii=False), encoding="utf-8")
    tmp.replace(run_dir / "manifest.json")


def read_manifest(run_dir: str | Path) -> dict:
    with open(Path(run_dir) / "manifest.json", encoding="utf-8") as f:
        return json.load(f)


def append_scoring(run_dir: str | Path, name: str, params: dict) -> None:
    run_dir = Path(run_dir)
    m = read_manifest(run_dir)
    m.setdefault("scoring", []).append({"name": name, "version": __version__,
                                        "timestamp": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"), "params": params})
    write_manifest(run_dir, m)


def existing_keys(run_dir: Path, redo_errors: bool = False) -> set[str]:
    path = run_dir / "traces.jsonl"
    keys: set[str] = set()
    if not path.exists():
        return keys
    for d in read_jsonl(path):
        if redo_errors and (d.get("meta") or {}).get("error"):
            continue
        keys.add(d["trace_key"])
    return keys


def _call_with_retry(client: ModelClient, req: GenerateRequest, retries: int = 3, backoff=(2.0, 8.0, 30.0), sleep=time.sleep):
    last: ClientError | None = None
    for attempt in range(retries + 1):
        try:
            return client.generate(req), attempt
        except ClientError as e:
            last = e
            if not e.retryable or attempt == retries:
                raise
            sleep(backoff[min(attempt, len(backoff) - 1)])
    raise last  # pragma: no cover


class ModelChanged(RuntimeError):
    pass


def run_experiment(jobs: list[Job], client: ModelClient, run_dir: str | Path, manifest: dict, prompt: dict, master_seed: int,
                   workers: int = 1, redo_errors: bool = False, force: bool = False, min_interval_ms: int = 0,
                   health_every: int = 100, progress: Callable[[str], None] | None = None, sleep=time.sleep,
                   sampling: dict | None = None, should_stop: Callable[[], bool] | None = None) -> dict:
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    sampling = sampling or {}
    manifest.setdefault("status", "running")
    write_manifest(run_dir, manifest)
    done = set() if force else existing_keys(run_dir, redo_errors)
    if force and (run_dir / "traces.jsonl").exists():
        (run_dir / "traces.jsonl").unlink()
    if redo_errors and (run_dir / "traces.jsonl").exists():
        keep = [d for d in read_jsonl(run_dir / "traces.jsonl") if not (d.get("meta") or {}).get("error")]
        write_jsonl(run_dir / "traces.jsonl", keep)
    todo = [j for j in jobs if j.trace_key not in done]
    model_tag = manifest["model"].get("tag")
    model_digest = manifest["model"].get("digest")
    server_version = manifest["model"].get("server_version")
    lock = threading.Lock()
    counts = {"done": len(done), "ok": 0, "errors": 0, "total": len(jobs)}
    started = time.time()
    out_path = run_dir / "traces.jsonl"
    stop = threading.Event()
    abort: list[Exception] = []
    q: queue.Queue = queue.Queue()
    for j in todo:
        q.put(j)
    last_call = [0.0]

    def log(msg: str) -> None:
        if progress:
            progress(msg)

    def health_check() -> None:
        d = client.describe()
        if d.get("digest") != model_digest or d.get("server_version") != server_version or d.get("tag") != model_tag:
            raise ModelChanged(f"model/server changed: {d}")

    def worker() -> None:
        while not stop.is_set():
            if should_stop is not None and should_stop():
                stop.set()
                return
            try:
                job = q.get_nowait()
            except queue.Empty:
                return
            try:
                if min_interval_ms:
                    with lock:
                        wait = last_call[0] + min_interval_ms / 1000 - time.time()
                        last_call[0] = max(time.time(), last_call[0] + min_interval_ms / 1000)
                    if wait > 0:
                        sleep(wait)
                seed = per_trace_seed(master_seed, job.trace_key)
                user = prompt["user_template"].replace("{case_rendered}", job.rendered) + f"\n<!-- trace_key: {job.trace_key} -->"
                req = GenerateRequest(system=prompt["system"], user=user, effort=job.effort, seed=seed,
                                      temperature=sampling.get("temperature", 1.0), top_p=sampling.get("top_p", 1.0),
                                      max_tokens=sampling.get("max_tokens", 8192), timeout_s=sampling.get("timeout_s", 600.0))
                meta = TraceMeta(seed=seed, temperature=req.temperature, timestamp=_dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"))
                try:
                    if hasattr(client, "kw"):
                        client.kw["meta"] = job.meta  # CallableClient / simulator receives variant metadata
                    resp, attempts = _call_with_retry(client, req, sleep=sleep)
                    meta.latency_ms = resp.latency_ms
                    meta.usage = resp.usage
                    meta.finish_reason = resp.finish_reason
                    meta.parse_warnings = list(resp.parse_warnings) + ([f"RETRIES:{attempts}"] if attempts else [])
                    trace = Trace(trace_key=job.trace_key, case_id=job.case_id, variant=job.variant, effort=job.effort, run=job.run,
                                  model=model_tag or "", reasoning=resp.reasoning, answer=resp.answer, server=manifest["model"].get("server"),
                                  prompt_id=prompt["id"], retrieved=[Retrieved(r.doc_id, r.chunk_id, r.text, r.score) for r in resp.retrieved],
                                  raw=resp.raw, meta=meta)
                    ok = True
                except ClientError as e:
                    meta.error = str(e)
                    trace = Trace(trace_key=job.trace_key, case_id=job.case_id, variant=job.variant, effort=job.effort, run=job.run,
                                  model=model_tag or "", reasoning="", answer="", server=manifest["model"].get("server"),
                                  prompt_id=prompt["id"], meta=meta)
                    ok = False
                with lock:
                    with open(out_path, "a", encoding="utf-8") as f:
                        f.write(trace.to_json() + "\n")
                        f.flush()
                    counts["done"] += 1
                    counts["ok" if ok else "errors"] += 1
                    n = counts["done"]
                    elapsed = time.time() - started
                    rate = (counts["ok"] + counts["errors"]) / elapsed if elapsed > 0 else 0
                    remaining = counts["total"] - n
                    eta = remaining / rate if rate > 0 else float("nan")
                    log(f"[{n}/{counts['total']}] {job.trace_key}  {'ok' if ok else 'ERROR'} {meta.latency_ms or 0}ms reasoning={len(trace.reasoning)}")
                    (run_dir / "progress.json").write_text(json.dumps({**counts, "elapsed_s": round(elapsed), "eta_s": None if eta != eta else round(eta)}))
                    if health_every and (counts["ok"] + counts["errors"]) % health_every == 0:
                        health_check()
            except Exception as e:  # noqa: BLE001
                abort.append(e)
                stop.set()
                return
            finally:
                q.task_done()

    try:
        health_check()
    except ModelChanged as e:
        manifest = read_manifest(run_dir)
        manifest["status"] = "aborted:model_changed"
        manifest["error"] = str(e)
        write_manifest(run_dir, manifest)
        raise
    threads = [threading.Thread(target=worker, daemon=True) for _ in range(max(1, workers))]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    manifest = read_manifest(run_dir)
    if should_stop is not None and should_stop() and not abort:
        manifest["status"] = "cancelled"
        manifest["n_traces"] = counts["done"]
        write_manifest(run_dir, manifest)
        counts["cancelled"] = True
        return counts
    if abort:
        manifest["status"] = f"aborted:{'model_changed' if isinstance(abort[0], ModelChanged) else type(abort[0]).__name__}"
        manifest["error"] = str(abort[0])
        write_manifest(run_dir, manifest)
        raise abort[0]
    manifest["status"] = "complete"
    manifest["finished"] = _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")
    manifest["n_traces"] = counts["done"]
    manifest["n_errors"] = sum(1 for d in read_jsonl(out_path) if (d.get("meta") or {}).get("error")) if out_path.exists() else 0
    manifest["wall_clock_s"] = round(time.time() - started, 1)
    write_manifest(run_dir, manifest)
    return counts


def manifest_check(run_dir: str | Path, lexicon: Lexicon | None = None) -> list[str]:
    lx = lexicon or lex_mod.load()
    m = read_manifest(run_dir)
    problems = []
    if m.get("status") != "complete":
        problems.append(f"status is {m.get('status')!r}")
    if m.get("git_dirty") and not m.get("allow_dirty"):
        problems.append("git tree was dirty at run time and no justification recorded")
    if not m.get("model", {}).get("digest") and m.get("model", {}).get("server") not in ("in-process",):
        problems.append("model digest absent")
    lex_sha = m.get("inputs", {}).get("lexicon", {}).get("sha256")
    if lex_sha and lex_sha != lx.sha256():
        problems.append("lexicon sha256 differs from the packaged lexicon")
    try:
        prompt = load_prompt(m["prompt"]["id"])
        if prompt["sha256"] != m["prompt"]["sha256"]:
            problems.append("prompt sha256 differs from the packaged prompt")
    except (OSError, KeyError):
        problems.append("prompt file not found")
    n, e = m.get("n_traces") or 0, m.get("n_errors") or 0
    if n and e / n > 0.02:
        problems.append(f"error rate {e}/{n} exceeds 2%")
    return problems
