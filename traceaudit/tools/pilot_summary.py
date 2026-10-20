"""Pilot measurements (spec 15 §3) from a scored run directory. Standard library only.

Run: python -m traceaudit.tools.pilot_summary runs/pilot --cases pilot/cases.jsonl \
        --claims-out pilot/labelled_claims_template.jsonl --n-claims 300

Writes <run_dir>/pilot_summary.json and, if requested, the clinician labelling template
(fields trace_key, claim_id, text, gold_assertions: []), stratified by effort x entity.
"""
from __future__ import annotations

import argparse
import json
import random
import re
import statistics
from collections import Counter, defaultdict
from pathlib import Path

LINES = ("Integrated diagnosis:", "Confidence:", "Key discriminating findings:", "Recommended further investigations:")
PRICE_PER_M = {"input": 4.0, "output": 20.0, "cache_read": 0.20, "cache_write": 5.0}  # claude-opus-5-5, USD


def _read(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def format_compliance(answer: str) -> dict:
    present = [bool(re.search(r"(?m)^\s*\**" + re.escape(l) + r"\**", answer)) for l in LINES]
    order_ok = all(present)
    if order_ok:
        idx = [re.search(r"(?m)^\s*\**" + re.escape(l), answer).start() for l in LINES]
        order_ok = idx == sorted(idx)
    # strict: nothing but the four labelled lines (blank lines allowed)
    body = [ln for ln in answer.splitlines() if ln.strip()]
    strict = all(present) and all(any(ln.strip().lstrip("*").startswith(l) for l in LINES) for ln in body)
    return {"lines_present": sum(present), "all_lines": all(present), "ordered": order_ok, "strict": strict}


def _pct(values: list[float], p: float) -> float | None:
    if not values:
        return None
    vals = sorted(values)
    k = max(0, min(len(vals) - 1, round(p * (len(vals) - 1))))
    return vals[k]


def _dist(values: list[float]) -> dict:
    if not values:
        return {"n": 0}
    return {"n": len(values), "mean": round(statistics.mean(values), 1), "median": _pct(values, 0.5), "p90": _pct(values, 0.9),
            "p99": _pct(values, 0.99), "max": max(values)}


def summarise(run_dir: Path, entity_of: dict[str, str]) -> dict:
    traces = _read(run_dir / "traces.jsonl")
    grounding = {g["trace_key"]: g for g in _read(run_dir / "grounding.jsonl")}
    claims = _read(run_dir / "claims.jsonl")
    summary = json.loads((run_dir / "summary.json").read_text()) if (run_dir / "summary.json").exists() else None
    ok = [t for t in traces if not (t.get("meta") or {}).get("error")]
    errors = [t for t in traces if (t.get("meta") or {}).get("error")]
    out: dict = {"run_dir": str(run_dir), "n_traces": len(traces), "n_ok": len(ok), "n_errors": len(errors),
                 "error_kinds": dict(Counter((t["meta"]["error"] or "").split(":")[0] for t in errors))}
    # -- format compliance
    comp = defaultdict(list)
    for t in ok:
        comp[t["effort"]].append(format_compliance(t["answer"]))
    out["format_compliance"] = {}
    for eff, rows in sorted(comp.items()):
        out["format_compliance"][eff] = {"n": len(rows), "all_lines_rate": round(sum(r["all_lines"] for r in rows) / len(rows), 4),
                                         "ordered_rate": round(sum(r["ordered"] for r in rows) / len(rows), 4),
                                         "strict_rate": round(sum(r["strict"] for r in rows) / len(rows), 4)}
    allrows = [r for rows in comp.values() for r in rows]
    out["format_compliance"]["all"] = {"n": len(allrows), "all_lines_rate": round(sum(r["all_lines"] for r in allrows) / max(1, len(allrows)), 4),
                                       "strict_rate": round(sum(r["strict"] for r in allrows) / max(1, len(allrows)), 4)}
    parsed = [g for g in grounding.values() if not g.get("error")]
    out["answer_parse"] = {"n": len(parsed), "unresolved": sum(1 for g in parsed if g.get("answer_entity") in (None, "UNRESOLVED")),
                           "hedged": sum(1 for g in parsed if g.get("answer_hedged")),
                           "correct_base": {eff: round(sum(1 for g in parsed if g["variant"] == "base" and g["effort"] == eff and g.get("answer_correct")) /
                                                        max(1, sum(1 for g in parsed if g["variant"] == "base" and g["effort"] == eff)), 4) for eff in ("low", "medium", "high")}}
    # -- base stability per (case, effort): majority entity share >= 0.6 with >= 3 answers
    pairs = defaultdict(list)
    for g in parsed:
        if g["variant"] == "base":
            pairs[(g["case_id"], g["effort"])].append(g.get("answer_entity"))
    stable = {}
    for (case, eff), ents in pairs.items():
        c = Counter(ents).most_common()
        share = c[0][1] / len(ents)
        tie = len(c) > 1 and c[0][1] == c[1][1]
        stable[(case, eff)] = (len(ents) >= 3 and share >= 0.6 and not tie, c[0][0], ents)
    out["base_stability"] = {"pairs": len(stable), "stable": sum(1 for v in stable.values() if v[0]),
                             "share_stable": round(sum(1 for v in stable.values() if v[0]) / max(1, len(stable)), 4),
                             "by_effort": {eff: round(sum(1 for (c, e), v in stable.items() if e == eff and v[0]) / max(1, sum(1 for (c, e) in stable if e == eff)), 4) for eff in ("low", "medium", "high")},
                             "unstable": [{"case_id": c, "effort": e, "answers": v[2]} for (c, e), v in sorted(stable.items()) if not v[0]]}
    # -- reasoning length and tokens per effort
    out["reasoning_length"] = {}
    for eff in ("low", "medium", "high"):
        rows = [t for t in ok if t["effort"] == eff]
        out["reasoning_length"][eff] = {"reasoning_chars": _dist([len(t["reasoning"]) for t in rows]),
                                        "reasoning_words": _dist([len(t["reasoning"].split()) for t in rows]),
                                        "answer_chars": _dist([len(t["answer"]) for t in rows]),
                                        "output_tokens": _dist([t["meta"]["usage"].get("output_tokens") or 0 for t in rows]),
                                        "latency_ms": _dist([t["meta"].get("latency_ms") or 0 for t in rows]),
                                        "finish_reasons": dict(Counter(t["meta"].get("finish_reason") for t in rows)),
                                        "no_reasoning": sum(1 for t in rows if not t["reasoning"])}
    # -- cost
    inp = sum(t["meta"]["usage"].get("input_tokens") or 0 for t in ok)
    outp = sum(t["meta"]["usage"].get("output_tokens") or 0 for t in ok)
    cr = sum(t["meta"]["usage"].get("cache_read_input_tokens") or 0 for t in ok)
    cw = sum(t["meta"]["usage"].get("cache_creation_input_tokens") or 0 for t in ok)
    out["usage"] = {"input_tokens": inp, "output_tokens": outp, "cache_read_input_tokens": cr, "cache_creation_input_tokens": cw,
                    "cost_usd": round(inp / 1e6 * PRICE_PER_M["input"] + outp / 1e6 * PRICE_PER_M["output"] + cr / 1e6 * PRICE_PER_M["cache_read"] + cw / 1e6 * PRICE_PER_M["cache_write"], 2),
                    "price_per_m": PRICE_PER_M}
    # -- grounding
    if summary:
        g = summary["grounding"]["pooled_rate"]
        out["grounding"] = {"pooled": {k: g.get(k) for k in ("point", "lo", "hi", "numerator", "denominator")},
                            "by_effort": {e: {k: v.get(k) for k in ("point", "lo", "hi")} for e, v in (g.get("by_effort") or {}).items()},
                            "label_counts": summary["grounding"].get("label_counts"), "claim_type_counts": summary["grounding"].get("claim_type_counts"),
                            "traces_with_contradiction": summary["grounding"].get("traces_with_contradiction"),
                            "traces_with_unsupported": summary["grounding"].get("traces_with_unsupported")}
        out["counts"] = summary.get("counts")
    out["claims"] = {"n": len(claims), "by_type": dict(Counter(c["type"] for c in claims)), "by_label": dict(Counter(c.get("label") for c in claims)),
                     "factual_by_effort": dict(Counter(c["trace_key"].split("|")[2] for c in claims if c["type"] == "factual"))}
    return out


def sample_claims(run_dir: Path, entity_of: dict[str, str], n: int, seed: int) -> list[dict]:
    """n factual claims stratified by effort x entity (equal allocation, remainder by seeded draw)."""
    claims = [c for c in _read(run_dir / "claims.jsonl") if c["type"] == "factual"]
    strata: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for c in claims:
        case_id, _v, effort, _r = c["trace_key"].split("|")
        strata[(effort, entity_of.get(case_id, case_id.split("-")[0]))].append(c)
    rng = random.Random(seed)
    keys = sorted(strata)
    per = n // len(keys) if keys else 0
    chosen: list[dict] = []
    leftovers: list[dict] = []
    for k in keys:
        pool = list(strata[k])
        rng.shuffle(pool)
        chosen += pool[:per]
        leftovers += pool[per:]
    rng.shuffle(leftovers)
    chosen += leftovers[: max(0, n - len(chosen))]
    chosen.sort(key=lambda c: (c["trace_key"], c["claim_id"]))
    return [{"trace_key": c["trace_key"], "claim_id": c["claim_id"], "text": c["text"], "gold_assertions": [],
             "_effort": c["trace_key"].split("|")[2], "_entity": entity_of.get(c["trace_key"].split("|")[0])}  # no extractor output: labelling stays blind
            for c in chosen]


def miss_candidates(run_dir: Path) -> list[dict]:
    """Heuristic scan for finding mentions the extractor did not assert (for lexicon extension review)."""
    pats = {
        "del_13q": r"\bdel ?13q|\b13q(?!\d)(?! deletion)|del\(13\)",
        "del_17p": r"\bdel ?17p|\b17p(?!\d)|del\(17\)",
        "del_11q": r"\bdel ?11q|\b11q(?!\d)",
        "trisomy_12": r"\btrisomy ?12\b|\+12\b",
        "t_11_14": r"t\(11;14\)|CCND1::IGH|CCND1-IGH|11;14",
        "t_14_18": r"t\(14;18\)|IGH::BCL2|BCL2::IGH|14;18",
        "BRAF_V600E": r"BRAF\b",
        "MYD88_L265P": r"MYD88\b",
        "TP53_mut": r"TP53\b",
        "IGHV_unmutated": r"IGHV\b",
        "CD5": r"\bCD5\b", "CD23": r"\bCD23\b", "CD10": r"\bCD10\b", "CD200": r"\bCD200\b", "CD103": r"\bCD103\b", "CD25": r"\bCD25\b", "CD11c": r"\bCD11c\b",
        "cyclin_D1": r"cyclin ?D1|CCND1", "SOX11": r"SOX11", "LEF1": r"LEF1", "annexin_A1": r"annexin",
        "hairy_cells": r"hairy cells?\b(?! leuk)", "smudge_cells": r"smudge", "prolymphocytes_increased": r"prolymphocyt",
        "splenomegaly": r"spleen|splenomegaly", "lymphadenopathy": r"lymphadenopathy|nodal (?:involvement|disease|sites)", "IgM_paraprotein": r"IgM (?:kappa |lambda )?paraprotein|IgM M-protein|monoclonal IgM",
    }
    out = []
    for c in _read(run_dir / "claims.jsonl"):
        if c["type"] not in ("factual", "other"):
            continue
        asserted = {a["finding_id"] for a in c.get("assertions", []) if a.get("polarity")}
        mentioned = {a["finding_id"] for a in c.get("assertions", [])}
        for fid, pat in pats.items():
            if re.search(pat, c["text"], re.I) and fid not in asserted:
                out.append({"finding_id": fid, "mentioned_unpolarised": fid in mentioned, "trace_key": c["trace_key"], "claim_id": c["claim_id"],
                            "type": c["type"], "label": c.get("label"), "text": c["text"][:240]})
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir"); ap.add_argument("--cases", required=True); ap.add_argument("--claims-out"); ap.add_argument("--n-claims", type=int, default=300)
    ap.add_argument("--seed", type=int, default=20261020); ap.add_argument("--misses-out")
    a = ap.parse_args(argv)
    run_dir = Path(a.run_dir)
    entity_of = {c["case_id"]: c["entity"] for c in _read(Path(a.cases))}
    s = summarise(run_dir, entity_of)
    if a.claims_out:
        rows = sample_claims(run_dir, entity_of, a.n_claims, a.seed)
        with open(a.claims_out, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        s["claims_template"] = {"path": a.claims_out, "n": len(rows), "by_effort": dict(Counter(r["_effort"] for r in rows)),
                                "by_entity": dict(Counter(r["_entity"] for r in rows))}
    if a.misses_out:
        m = miss_candidates(run_dir)
        with open(a.misses_out, "w", encoding="utf-8") as f:
            for r in m:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        s["miss_candidates"] = {"path": a.misses_out, "n": len(m), "by_finding": dict(Counter(r["finding_id"] for r in m).most_common())}
    (run_dir / "pilot_summary.json").write_text(json.dumps(s, indent=1), encoding="utf-8")
    print(json.dumps(s, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
