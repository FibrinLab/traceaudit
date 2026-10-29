"""Provenance hashes: which prompt produced which trace, and which inputs a run committed to.

A hash answers one question, "is this byte-for-byte the same?", so these fields prove identity
(no post-hoc editing of traces, no variant text hidden in a prompt, inputs fixed before the run)
and say nothing about whether the reasoning is faithful; that is the job of the probes.

Per trace (`trace.provenance`):
    prompt_sha256     sha256(system + "\\x00" + user) of the exact strings sent to the model
    reasoning_sha256  sha256 of the raw reasoning as stored
    answer_sha256     sha256 of the raw answer as stored
Per run (`manifest.provenance`):
    inputs_sha256     sha256 over "name=sha256" lines for prompt, cases, perturbations, lexicon,
                      the value to put in a pre-registration before any model is called
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .schema import read_jsonl
from .textutil import sha256_file, sha256_text

RULE = "sha256(utf8); prompt = sha256(system + '\\x00' + user); inputs = sha256('\\n'.join(name=sha256 or none))"
INPUT_NAMES = ("prompt", "cases", "perturbations", "lexicon")
PROMPT_SEP = "\x00"


def prompt_sha256(system: str, user: str) -> str:
    return sha256_text((system or "") + PROMPT_SEP + (user or ""))


def trace_hashes(system: str, user: str, reasoning: str | None, answer: str | None) -> dict[str, str | None]:
    return {"prompt_sha256": prompt_sha256(system, user),
            "reasoning_sha256": sha256_text(reasoning) if reasoning is not None else None,
            "answer_sha256": sha256_text(answer) if answer is not None else None}


def inputs_sha256(components: dict[str, str | None]) -> str:
    return sha256_text("\n".join(f"{k}={components.get(k) or 'none'}" for k in INPUT_NAMES))


def manifest_provenance(prompt_sha: str | None, cases_sha: str | None, perts_sha: str | None, lexicon_sha: str | None) -> dict[str, Any]:
    comps = {"prompt": prompt_sha, "cases": cases_sha, "perturbations": perts_sha, "lexicon": lexicon_sha}
    return {"rule": RULE, "components": comps, "inputs_sha256": inputs_sha256(comps)}


def _manifest_components(m: dict) -> dict[str, str | None]:
    inputs = m.get("inputs") or {}
    return {"prompt": (m.get("prompt") or {}).get("sha256"),
            "cases": (inputs.get("cases") or {}).get("sha256"),
            "perturbations": (inputs.get("perturbations") or {}).get("sha256"),
            "lexicon": (inputs.get("lexicon") or {}).get("sha256")}


def verify_run(run_dir: str | Path, rendered: dict[str, str] | None = None, check_files: bool = True) -> dict[str, Any]:
    """Recompute every hash a run recorded. `rendered` maps trace_key -> the rendered case text, so the prompt hash
    can be rebuilt from the manifest's prompt; without it prompts count as unverified, not as failures."""
    run_dir = Path(run_dir)
    with open(run_dir / "manifest.json", encoding="utf-8") as f:
        m = json.load(f)
    problems: list[str] = []
    counts = {"traces": 0, "with_provenance": 0, "reasoning_ok": 0, "answer_ok": 0, "prompt_ok": 0, "prompt_unverified": 0, "mismatches": 0}
    mismatches: list[dict[str, str]] = []

    prov = m.get("provenance")
    comps = _manifest_components(m)
    if prov is None:
        problems.append("manifest has no provenance block (run predates provenance hashes)")
    else:
        if prov.get("components") != comps:
            problems.append("manifest provenance components differ from the recorded input hashes")
        if prov.get("inputs_sha256") != inputs_sha256(comps):
            problems.append("inputs_sha256 does not match the recorded components")
    p = m.get("prompt") or {}
    if p.get("system") is not None and p.get("user_template") is not None and p.get("sha256"):
        if sha256_text(p["system"] + "\n" + p["user_template"]) != p["sha256"]:
            problems.append("prompt sha256 does not match the prompt text stored in the manifest")
    if check_files:
        for name in ("cases", "perturbations"):
            rec = (m.get("inputs") or {}).get(name) or {}
            path, sha = rec.get("path"), rec.get("sha256")
            if path and sha and Path(path).exists() and sha256_file(path) != sha:
                problems.append(f"{name} file at {path} no longer matches its recorded sha256")

    embed = bool(p.get("embed_trace_key"))
    traces_path = run_dir / "traces.jsonl"
    for d in read_jsonl(traces_path) if traces_path.exists() else []:
        counts["traces"] += 1
        pv = d.get("provenance")
        if not pv:
            continue
        counts["with_provenance"] += 1
        tk = d["trace_key"]
        for field_, key in (("reasoning", "reasoning_sha256"), ("answer", "answer_sha256")):
            want = pv.get(key)
            if want is None:
                continue
            got = sha256_text(d.get(field_) or "")
            if got == want:
                counts[f"{field_}_ok"] += 1
            else:
                counts["mismatches"] += 1
                mismatches.append({"trace_key": tk, "field": field_, "recorded": want, "recomputed": got})
        want = pv.get("prompt_sha256")
        if want is None or rendered is None or tk not in rendered or p.get("system") is None or p.get("user_template") is None:
            counts["prompt_unverified"] += 1
            continue
        user = p["user_template"].replace("{case_rendered}", rendered[tk])
        if embed:
            user += f"\n<!-- trace_key: {tk} -->"
        got = prompt_sha256(p["system"], user)
        if got == want:
            counts["prompt_ok"] += 1
        else:
            counts["mismatches"] += 1
            mismatches.append({"trace_key": tk, "field": "prompt", "recorded": want, "recomputed": got})
    if counts["traces"] and not counts["with_provenance"]:
        problems.append("no trace carries provenance hashes (run predates provenance hashes)")
    if mismatches:
        problems.append(f"{len(mismatches)} hash mismatch(es) across {counts['traces']} traces")
    return {"ok": not problems, "problems": problems, "counts": counts, "mismatches": mismatches[:50],
            "inputs_sha256": (prov or {}).get("inputs_sha256")}
