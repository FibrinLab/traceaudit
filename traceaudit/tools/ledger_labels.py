"""Blind labelling and agreement for the ledger grader (spec 19).

`ledger.grade_segment` grades every citation by rule and reports no error of its own. To measure that error, two
raters label a sample of citations without seeing the grader's grade, disagreements are adjudicated, and the
grader is compared with the rater consensus. This module builds the sample, the per-rater files and the report.
Everything is a function of the audit result, so it is domain-agnostic. Standard library only.

Files in a label set directory:
  grader.jsonl        every sampled item with the grader's `grade` (and its extracted `stated` polarity)
  <rater>.jsonl       the same items, shuffled per rater, with `human_grade` and `note` to fill in
  adjudicated.jsonl   optional: {item_id, human_grade} for items the raters disagreed on
  manifest.json       seed, n, raters, source files and stratum counts
"""
from __future__ import annotations

import hashlib
import json
import math
import random
from collections import Counter, defaultdict
from pathlib import Path
from typing import Sequence

from .. import ledger, stats
from ..schema import read_jsonl, write_jsonl

HUMAN_GRADES = ("agree", "disagree", "unverifiable", "not_mentioned")
GRADER_ONLY = ("grade", "stated")   # never written to a rater file
RESERVED_FILES = ("grader", "adjudicated", "agreement")


def item_id(case_id: str, section: str, segment_text: str, fact_id: str | None) -> str:
    """Stable id for one (case, section, sentence, fact) tuple."""
    key = "\x1f".join([case_id or "", section or "", segment_text or "", fact_id or ""])
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


# ----------------------------------------------------------------------------- items

def _case_from_result(result: dict) -> ledger.LedgerCase:
    facts = [ledger.Fact(f["id"], f["source"], f["section"], f["field"], f["value"], f.get("evidence") or "", f.get("candidate"))
             for f in result.get("facts", [])]
    return ledger.LedgerCase(result["case_id"], result.get("truth"), list(result.get("candidates") or []), facts)


def rationale_segments(result: dict) -> list[tuple[str, ledger.Segment]]:
    """The rationale's citing sentences as (section, segment): key findings, differential entries and discriminators.
    Criteria rows are left out: they state what a candidate would require, not what the patient has. The audit
    result does not grade rationale text, so `items_from_audit` grades it here with `ledger.grade_segment`."""
    rat = result.get("rationale")
    if not rat:
        return []
    out: list[tuple[str, ledger.Segment]] = []
    for kf in rat.get("key_findings") or []:
        if kf.get("description") and kf.get("ids"):
            out.append(("rationale.key_findings", ledger.Segment(kf["description"], list(kf["ids"]))))
    for d in rat.get("differential") or []:
        ids = list(d.get("supporting") or []) + list(d.get("contradicting") or [])
        if d.get("rationale") and ids:
            out.append((f"rationale.differential.{d['diagnosis']}", ledger.Segment(d["rationale"], ids)))
    for d in rat.get("discriminators") or []:
        if d.get("text") and d.get("ids"):
            out.append(("rationale.discriminators", ledger.Segment(d["text"], list(d["ids"]))))
    return out


def items_from_audit(result: dict) -> list[dict]:
    """One item per cited fact in every report segment and rationale sentence, and per uncited assertion the grader
    matched to a fact. Only grades a human can give (`HUMAN_GRADES`) become items: `reference` and `not_found`
    citations are mechanical (the id's source or existence) and are left out, as are uncited assertions whose
    field matches no fact. Items are unique by `item_id`, in document order."""
    case_id = result["case_id"]
    facts = {f["id"]: f for f in result.get("facts", [])}
    seen: dict[str, dict] = {}

    def add(source: str, section: str, graded: dict) -> None:
        text = graded["text"]
        for c in graded["cited"]:
            if c["grade"] not in HUMAN_GRADES:
                continue
            f = facts.get(c["id"], {})
            iid = item_id(case_id, section, text, c["id"])
            seen.setdefault(iid, {"item_id": iid, "case_id": case_id, "source": source, "section": section, "segment_text": text,
                                  "fact_id": c["id"], "field": c.get("field"), "value": c.get("value"), "evidence": f.get("evidence") or "",
                                  "kind": "citation", "stated": c.get("stated"), "grade": c["grade"]})
        for u in graded["uncited_assertions"]:
            if u["grade"] not in HUMAN_GRADES or not u.get("fact_id"):
                continue
            f = facts.get(u["fact_id"], {})
            iid = item_id(case_id, section, text, u["fact_id"])
            seen.setdefault(iid, {"item_id": iid, "case_id": case_id, "source": source, "section": section, "segment_text": text,
                                  "fact_id": u["fact_id"], "field": u.get("field"), "value": u.get("value"), "evidence": f.get("evidence") or "",
                                  "kind": "uncited", "stated": u.get("stated"), "grade": u["grade"]})

    for sec in result.get("sections", []):
        for g in sec["segments"]:
            add("report", sec["title"], g)
    rat_segs = rationale_segments(result)
    if rat_segs:
        case = _case_from_result(result)
        lx = ledger.lexicon_from_case(case)
        for section, seg in rat_segs:
            add("rationale", section, ledger.grade_segment(seg, case, lx))
    return list(seen.values())


# ----------------------------------------------------------------------------- sampling

def strata_counts(items: Sequence[dict]) -> dict[str, int]:
    return {f"{g}|{s}": n for (g, s), n in sorted(Counter((i["grade"], i["source"]) for i in items).items())}


def sample(items: Sequence[dict], n: int, seed: int, per_case: int | None = None) -> list[dict]:
    """Up to `n` items, round-robin over grade x source strata (so rare grades are over-represented relative to
    their frequency), at most `per_case` items from any one case (default: twice the even share, at least 5).
    Deterministic for a given seed whatever the input order. Sorted by (case_id, item_id)."""
    n_cases = len({i["case_id"] for i in items})
    if per_case is None:
        per_case = max(5, math.ceil(2 * n / max(1, n_cases)))
    strata: dict[tuple, list[dict]] = defaultdict(list)
    for it in sorted(items, key=lambda i: i["item_id"]):
        strata[(it["grade"], it["source"])].append(it)
    rng = random.Random(seed)
    keys = sorted(strata)
    for k in keys:
        rng.shuffle(strata[k])
    taken: Counter = Counter()
    out: list[dict] = []
    progressed = True
    while len(out) < n and progressed:
        progressed = False
        for k in keys:
            while strata[k] and len(out) < n:
                it = strata[k].pop()
                if taken[it["case_id"]] >= per_case:
                    continue
                taken[it["case_id"]] += 1
                out.append(it)
                progressed = True
                break
    return sorted(out, key=lambda i: (i["case_id"], i["item_id"]))


def rater_files(sampled: Sequence[dict], raters: Sequence[str], seed: int) -> dict[str, list[dict]]:
    """The same items for every rater, each in its own seeded order, without the grader's fields and with empty
    `human_grade` and `note` to fill in."""
    out: dict[str, list[dict]] = {}
    for r in raters:
        rows = []
        for it in sampled:
            context = {k: v for k, v in it.items() if k not in GRADER_ONLY and k != "item_id"}
            rows.append({"item_id": it["item_id"], "rater_id": r, "human_grade": "", "note": "", **context})
        random.Random(f"{seed}:{r}").shuffle(rows)
        out[r] = rows
    return out


def write_label_set(out_dir: str | Path, sampled: Sequence[dict], raters: Sequence[str], seed: int, meta: dict | None = None) -> dict[str, Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {"grader": out_dir / "grader.jsonl"}
    write_jsonl(paths["grader"], sampled)
    for r, rows in rater_files(sampled, raters, seed).items():
        paths[r] = out_dir / f"{r}.jsonl"
        write_jsonl(paths[r], rows)
    manifest = {"seed": seed, "n": len(sampled), "raters": list(raters), "n_cases": len({i["case_id"] for i in sampled}),
                "strata": strata_counts(sampled), "human_grades": list(HUMAN_GRADES), **(meta or {})}
    paths["manifest"] = out_dir / "manifest.json"
    paths["manifest"].write_text(json.dumps(manifest, indent=1, ensure_ascii=False), encoding="utf-8")
    return paths


def read_label_set(labels_dir: str | Path, adjudicated: str | Path | None = None) -> tuple[list[dict], dict[str, list[dict]], list[dict] | None]:
    """grader rows, {rater_id: rows} for every other *.jsonl in the directory, adjudicated rows (if given or present)."""
    labels_dir = Path(labels_dir)
    grader = list(read_jsonl(labels_dir / "grader.jsonl"))
    raters: dict[str, list[dict]] = {}
    for p in sorted(labels_dir.glob("*.jsonl")):
        if p.stem in RESERVED_FILES:
            continue
        rows = list(read_jsonl(p))
        rid = next((r.get("rater_id") for r in rows if r.get("rater_id")), None) or p.stem
        raters[rid] = rows
    adj_path = Path(adjudicated) if adjudicated else labels_dir / "adjudicated.jsonl"
    adj = list(read_jsonl(adj_path)) if adj_path.exists() else None
    return grader, raters, adj


# ----------------------------------------------------------------------------- agreement

def _grade(row: dict) -> str | None:
    g = (row.get("human_grade") or "").strip().lower()
    return g or None


def _ci(records: list, statistic, B: int, seed: int) -> dict:
    """Percentile CI clustered by case_id (records[i][0]); item-level resampling when fewer than 5 cases."""
    if not records:
        return stats._boot(float("nan"), float("nan"), float("nan"), 0, 0, 0, "none")
    n_cases = len({r[0] for r in records})
    if n_cases < 5:
        return stats.agreement_bootstrap(statistic, list(records), B, seed)
    return stats.cluster_bootstrap(records, lambda r: r[0], statistic, B, seed)


def _kappa_stat(rs: list) -> float:
    return stats.cohen_kappa([r[1] for r in rs], [r[2] for r in rs])


def _pct_stat(rs: list) -> float:
    """Exact agreement for nominal labels (stats.percent_agreement is for integer scores)."""
    return sum(1 for r in rs if r[1] == r[2]) / len(rs) if rs else float("nan")


def _nominal_pct(a: list, b: list) -> float:
    return _pct_stat(list(zip([None] * len(a), a, b)))


def agreement(rater_rows: dict[str, list[dict]], grader_rows: list[dict], adjudicated: list[dict] | None = None,
              B: int = 2000, seed: int = 20261029, margin: float = 0.1) -> dict:
    """Inter-rater agreement, consensus, and grader vs consensus with case-clustered bootstrap CIs.

    Consensus per item: the raters' label when they all agree; otherwise the adjudicated label; otherwise a strict
    majority (three or more raters); otherwise unresolved and excluded. Acceptance (spec 19): the grader's kappa with
    the consensus is at least the mean pairwise inter-rater kappa minus `margin`."""
    grader = {r["item_id"]: r for r in grader_rows}
    items = sorted(grader)
    case_of = {iid: grader[iid]["case_id"] for iid in items}
    problems: list[str] = []
    labels: dict[str, dict[str, str | None]] = {}
    n_unlabelled = n_invalid = 0
    for rid, rows in rater_rows.items():
        lab: dict[str, str | None] = {}
        for row in rows:
            iid = row.get("item_id")
            if iid not in grader:
                problems.append(f"{rid}: item {iid} is not in grader.jsonl")
                continue
            g = _grade(row)
            if g is not None and g not in HUMAN_GRADES:
                problems.append(f"{rid}: item {iid} has unknown grade {g!r}")
                n_invalid += 1
                g = None
            lab[iid] = g
        for iid in items:
            if lab.get(iid) is None:
                n_unlabelled += 1
                lab.setdefault(iid, None)
        labels[rid] = lab
    raters = sorted(labels)
    adj: dict[str, str] = {}
    for row in adjudicated or []:
        g = _grade(row)
        if g in HUMAN_GRADES and row.get("item_id") in grader:
            adj[row["item_id"]] = g
        elif g is not None:
            problems.append(f"adjudicated: item {row.get('item_id')} has unknown grade {g!r}")

    # inter-rater
    pairwise: dict[str, dict] = {}
    kappas: list[float] = []
    for i, a in enumerate(raters):
        for b in raters[i + 1:]:
            recs = [(case_of[iid], labels[a][iid], labels[b][iid]) for iid in items if labels[a][iid] is not None and labels[b][iid] is not None]
            k = _ci(recs, _kappa_stat, B, seed)
            pairwise[f"{a}|{b}"] = {"n": len(recs), "cohen_kappa": k, "percent_agreement": _ci(recs, _pct_stat, B, seed)}
            if k["point"] is not None:
                kappas.append(k["point"])
    matrix = [(case_of[iid], [labels[r][iid] for r in raters]) for iid in items]
    gwet = _ci(matrix, lambda rs: stats.gwet_ac1([m for _, m in rs], HUMAN_GRADES), B, seed) if len(raters) >= 2 else None

    # consensus
    consensus: dict[str, str] = {}
    source: Counter = Counter()
    n_disagree = n_unresolved = 0
    need = min(2, len(raters))
    for iid in items:
        votes = [labels[r][iid] for r in raters if labels[r][iid] is not None]
        if len(votes) < need or not votes:
            n_unresolved += 1
            continue
        if len(set(votes)) == 1:
            consensus[iid] = votes[0]
            source["unanimous"] += 1
            continue
        n_disagree += 1
        if iid in adj:
            consensus[iid] = adj[iid]
            source["adjudicated"] += 1
            continue
        top, top_n = Counter(votes).most_common(1)[0]
        if top_n * 2 > len(votes):
            consensus[iid] = top
            source["majority"] += 1
        else:
            n_unresolved += 1

    # grader vs consensus
    recs = [(case_of[iid], grader[iid]["grade"], consensus[iid]) for iid in items if iid in consensus]
    pred = [r[1] for r in recs]
    truth = [r[2] for r in recs]
    confusion = {t: {p: 0 for p in HUMAN_GRADES} for t in HUMAN_GRADES}
    for p, t in zip(pred, truth):
        confusion.setdefault(t, {}).setdefault(p, 0)
        confusion[t][p] += 1
    gk = _ci(recs, _kappa_stat, B, seed)
    gvc = {"n": len(recs), "cohen_kappa": gk, "percent_agreement": _ci(recs, _pct_stat, B, seed),
           "per_class": {c: {**v, "precision": stats._r(v["precision"]), "recall": stats._r(v["recall"])}
                         for c, v in stats.per_class_pr(pred, truth, HUMAN_GRADES).items()},
           "confusion": confusion, "confusion_layout": "rows = consensus, columns = grader"}
    gvr = {}
    for r in raters:
        pairs = [(grader[iid]["grade"], labels[r][iid]) for iid in items if labels[r][iid] is not None]
        gvr[r] = {"n": len(pairs), "cohen_kappa": stats._r(stats.cohen_kappa([p for p, _ in pairs], [t for _, t in pairs])),
                  "percent_agreement": stats._r(_nominal_pct([p for p, _ in pairs], [t for _, t in pairs]))}
    inter = sum(kappas) / len(kappas) if kappas else None
    threshold = stats._r(inter - margin) if inter is not None else None
    accepted = None if inter is None or gk["point"] is None else bool(gk["point"] >= inter - margin)
    return {
        "n_items": len(items), "n_cases": len(set(case_of.values())), "raters": raters,
        "n_unlabelled": n_unlabelled, "n_invalid": n_invalid, "n_disagreements_between_raters": n_disagree,
        "n_consensus": len(consensus), "n_unresolved": n_unresolved, "consensus_source": dict(source),
        "label_counts": {"grader": dict(sorted(Counter(grader[iid]["grade"] for iid in items).items())),
                         **{r: dict(sorted(Counter(v for v in labels[r].values() if v is not None).items())) for r in raters}},
        "inter_rater": {"pairwise": pairwise, "mean_cohen_kappa": stats._r(inter), "gwet_ac1": gwet},
        "grader_vs_consensus": gvc, "grader_vs_rater": gvr,
        "acceptance": {"rule": f"grader kappa >= inter-rater kappa - {margin}", "inter_rater_kappa": stats._r(inter),
                       "grader_kappa": gk["point"], "threshold": threshold, "accepted": accepted},
        "bootstrap": {"B": B, "seed": seed, "cluster": "case_id (item-level when fewer than 5 cases)"},
        "problems": problems,
    }


def summary_text(rep: dict) -> str:
    """A few lines for the terminal."""
    def ci(d):
        if not d or d.get("point") is None:
            return "n/a"
        return f"{d['point']:.3f} [{d['lo']:.3f}, {d['hi']:.3f}]" if d.get("lo") is not None else f"{d['point']:.3f}"
    lines = [f"{rep['n_items']} items from {rep['n_cases']} case(s); raters {', '.join(rep['raters']) or 'none'}; "
             f"{rep['n_unlabelled']} unlabelled, {rep['n_invalid']} invalid; {rep['n_disagreements_between_raters']} rater disagreements; "
             f"consensus on {rep['n_consensus']}, {rep['n_unresolved']} unresolved"]
    for pair, d in rep["inter_rater"]["pairwise"].items():
        lines.append(f"inter-rater {pair}: kappa {ci(d['cohen_kappa'])}, agreement {ci(d['percent_agreement'])} (n {d['n']})")
    if rep["inter_rater"]["gwet_ac1"]:
        lines.append(f"Gwet AC1 over raters: {ci(rep['inter_rater']['gwet_ac1'])}")
    g = rep["grader_vs_consensus"]
    lines.append(f"grader vs consensus: kappa {ci(g['cohen_kappa'])}, agreement {ci(g['percent_agreement'])} (n {g['n']})")
    for c, v in g["per_class"].items():
        lines.append(f"  {c:14} precision {v['precision'] if v['precision'] is not None else 'n/a'} recall {v['recall'] if v['recall'] is not None else 'n/a'} (support {v['support']})")
    a = rep["acceptance"]
    verdict = "accepted" if a["accepted"] else ("not accepted" if a["accepted"] is False else "undetermined")
    lines.append(f"acceptance ({a['rule']}): {verdict}; grader {a['grader_kappa']} vs threshold {a['threshold']}")
    for p in rep["problems"][:10]:
        lines.append(f"problem: {p}")
    return "\n".join(lines)


def artefact_paths(source: str | Path) -> list[Path]:
    p = Path(source)
    if p.is_dir():
        return sorted(q for q in p.rglob("*.md") if q.is_file())
    return [p]
