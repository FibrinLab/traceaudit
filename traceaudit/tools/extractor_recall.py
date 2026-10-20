"""Extractor recall against clinician-labelled claims (spec 03 §5).

labelled_claims.jsonl: {trace_key, claim_id, gold_assertions: [{finding_id, polarity}]}
"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from ..schema import load_claims, read_jsonl


def measure(labelled_path: str | Path, run_dir: str | Path) -> dict:
    claims = {(c.trace_key, c.claim_id): c for c in load_claims(Path(run_dir) / "claims.jsonl")}
    tp = fp = fn = 0
    per: dict[str, dict[str, int]] = defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0})
    polarity_confusion = {"pos->neg": 0, "neg->pos": 0}
    n = 0
    for row in read_jsonl(labelled_path):
        c = claims.get((row["trace_key"], row["claim_id"]))
        if c is None:
            continue
        n += 1
        gold = {(g["finding_id"], g["polarity"]) for g in row["gold_assertions"]}
        got = {(a.finding_id, a.polarity) for a in c.assertions if a.polarity}
        for f, p in got & gold:
            tp += 1; per[f]["tp"] += 1
        for f, p in got - gold:
            fp += 1; per[f]["fp"] += 1
            if (f, "neg" if p == "pos" else "pos") in gold:
                polarity_confusion[f"{'neg' if p == 'pos' else 'pos'}->{p}"] += 1
        for f, p in gold - got:
            fn += 1; per[f]["fn"] += 1
    prec = tp / (tp + fp) if tp + fp else None
    rec = tp / (tp + fn) if tp + fn else None
    return {"claims": n, "tp": tp, "fp": fp, "fn": fn, "precision": prec, "recall": rec, "polarity_confusion": polarity_confusion,
            "per_finding": {f: {**v, "recall": v["tp"] / (v["tp"] + v["fn"]) if v["tp"] + v["fn"] else None} for f, v in sorted(per.items())}}
