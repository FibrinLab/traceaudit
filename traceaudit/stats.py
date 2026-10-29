"""Statistics: Wilson, case-clustered bootstrap, agreement, long export, summary (spec 09). Standard library only."""
from __future__ import annotations

import csv
import json
import math
import random
from collections import defaultdict
from pathlib import Path
from typing import Callable, Iterable, Sequence

from .schema import read_jsonl

Z95 = 1.959964


def wilson(k: int, n: int, z: float = Z95) -> tuple[float, float]:
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def _percentile(sorted_vals: list[float], q: float) -> float:
    if not sorted_vals:
        return float("nan")
    idx = q * (len(sorted_vals) - 1)
    lo = math.floor(idx)
    hi = math.ceil(idx)
    if lo == hi:
        return sorted_vals[lo]
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (idx - lo)


def cluster_bootstrap(records: Sequence, cluster_key: Callable, statistic: Callable[[list], float], B: int = 2000,
                      seed: int = 20261020, alpha: float = 0.05) -> dict:
    """Percentile interval of `statistic` over cluster resamples [PRE-REG]."""
    clusters: dict = defaultdict(list)
    for r in records:
        clusters[cluster_key(r)].append(r)
    keys = list(clusters)
    point = statistic(list(records)) if records else float("nan")
    if not keys:
        return _boot(point, float("nan"), float("nan"), B, 0, 0, "cluster-percentile")
    rng = random.Random(seed)
    vals = []
    drops = 0
    for _ in range(B):
        sample = []
        for _ in keys:
            sample.extend(clusters[rng.choice(keys)])
        v = statistic(sample)
        if v is None or (isinstance(v, float) and math.isnan(v)):
            drops += 1
            continue
        vals.append(v)
    vals.sort()
    out = _boot(point, _percentile(vals, alpha / 2), _percentile(vals, 1 - alpha / 2), B, len(keys), len(records), "cluster-percentile")
    out["dropped"] = drops
    return out


def _boot(point, lo, hi, B, n_clusters, n_records, method) -> dict:
    return {"point": _r(point), "lo": _r(lo), "hi": _r(hi), "B": B, "n_clusters": n_clusters, "n_records": n_records, "method": method,
            "ci_method": "bootstrap" if method.startswith("cluster") else method}


def _r(x):
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return None
    return round(float(x), 4)


def rate_ci(cells: list[tuple[str, float, float]], B: int = 2000, seed: int = 20261020, min_clusters: int = 5) -> dict:
    """cells = [(cluster, numerator, denominator)] per record. Ratio-of-sums with case-clustered percentile CI;
    Wilson when fewer than `min_clusters` clusters."""
    by_c: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0])
    for c, num, den in cells:
        by_c[c][0] += num
        by_c[c][1] += den
    keys = list(by_c)
    tot_num = sum(v[0] for v in by_c.values())
    tot_den = sum(v[1] for v in by_c.values())
    point = tot_num / tot_den if tot_den else float("nan")
    out: dict
    if tot_den == 0:
        out = _boot(float("nan"), float("nan"), float("nan"), 0, len(keys), len(cells), "none")
    elif len(keys) < min_clusters:
        lo, hi = wilson(int(round(tot_num)), int(round(tot_den)))
        out = _boot(point, lo, hi, 0, len(keys), len(cells), "wilson")
    else:
        rng = random.Random(seed)
        vals = []
        sums = [by_c[k] for k in keys]
        n = len(keys)
        for _ in range(B):
            num = den = 0.0
            for _ in range(n):
                s = sums[rng.randrange(n)]
                num += s[0]
                den += s[1]
            if den:
                vals.append(num / den)
        vals.sort()
        out = _boot(point, _percentile(vals, 0.025), _percentile(vals, 0.975), B, len(keys), len(cells), "cluster-percentile")
    out["numerator"] = _r(tot_num)
    out["denominator"] = _r(tot_den)
    return out


def paired_difference(cells_a: list[tuple[str, float, float]], cells_b: list[tuple[str, float, float]], B: int = 2000, seed: int = 20261020) -> dict:
    """Difference of two ratio-of-sums rates using the same cluster draw for both arms."""
    def sums(cells):
        d: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0])
        for c, n, m in cells:
            d[c][0] += n
            d[c][1] += m
        return d
    sa, sb = sums(cells_a), sums(cells_b)
    keys = sorted(set(sa) | set(sb))
    def rate(s):
        n = sum(v[0] for v in s.values()); m = sum(v[1] for v in s.values())
        return n / m if m else float("nan")
    point = rate(sa) - rate(sb)
    if len(keys) < 5:
        return _boot(point, float("nan"), float("nan"), 0, len(keys), len(cells_a) + len(cells_b), "none")
    rng = random.Random(seed)
    vals = []
    n = len(keys)
    for _ in range(B):
        na = da = nb = db = 0.0
        for _ in range(n):
            k = keys[rng.randrange(n)]
            if k in sa:
                na += sa[k][0]; da += sa[k][1]
            if k in sb:
                nb += sb[k][0]; db += sb[k][1]
        if da and db:
            vals.append(na / da - nb / db)
    vals.sort()
    return _boot(point, _percentile(vals, 0.025), _percentile(vals, 0.975), B, n, len(cells_a) + len(cells_b), "cluster-percentile")


# ----------------------------------------------------------------------------- agreement

def _weights(k: int, kind: str) -> list[list[float]]:
    w = [[0.0] * k for _ in range(k)]
    for i in range(k):
        for j in range(k):
            d = abs(i - j) / (k - 1) if k > 1 else 0.0
            w[i][j] = 1 - d if kind == "linear" else 1 - d * d
    return w


def weighted_kappa(a: Sequence[int], b: Sequence[int], k: int = 4, weights: str = "linear", low: int = 1) -> float:
    pairs = [(x - low, y - low) for x, y in zip(a, b) if x is not None and y is not None]
    n = len(pairs)
    if n == 0:
        return float("nan")
    w = _weights(k, weights)
    obs = [[0.0] * k for _ in range(k)]
    for x, y in pairs:
        obs[x][y] += 1
    ra = [sum(obs[i]) for i in range(k)]
    rb = [sum(obs[i][j] for i in range(k)) for j in range(k)]
    po = sum(w[i][j] * obs[i][j] for i in range(k) for j in range(k)) / n
    pe = sum(w[i][j] * ra[i] * rb[j] for i in range(k) for j in range(k)) / (n * n)
    if pe == 1:
        return 1.0
    return (po - pe) / (1 - pe)


def gwet_ac2(matrix: Sequence[Sequence], k: int = 4, weights: str = "linear", low: int = 1) -> float:
    """Gwet's AC2 for ordinal ratings; matrix rows = items, columns = raters (None = missing)."""
    w = _weights(k, weights)
    n_items = 0
    pa_sum = 0.0
    pi = [0.0] * k
    rows = []
    for row in matrix:
        r = [x - low for x in row if x is not None]
        if len(r) < 2:
            continue
        rows.append(r)
    n = len(rows)
    if n == 0:
        return float("nan")
    for r in rows:
        m = len(r)
        counts = [0] * k
        for x in r:
            counts[x] += 1
        # weighted agreement for the item
        agree = 0.0
        for q in range(k):
            r_star = sum(w[q][j] * counts[j] for j in range(k))
            agree += counts[q] * (r_star - 1)
        pa_sum += agree / (m * (m - 1))
        for q in range(k):
            pi[q] += counts[q] / m
        n_items += 1
    pa = pa_sum / n_items
    pi = [p / n_items for p in pi]
    tw = sum(sum(row) for row in w)
    pe = tw / (k * (k - 1)) * sum(p * (1 - p) for p in pi)
    if pe == 1:
        return 1.0
    return (pa - pe) / (1 - pe)


def percent_agreement(a: Sequence[int], b: Sequence[int], within: int = 0) -> float:
    pairs = [(x, y) for x, y in zip(a, b) if x is not None and y is not None]
    if not pairs:
        return float("nan")
    return sum(1 for x, y in pairs if abs(x - y) <= within) / len(pairs)


def agreement_bootstrap(fn: Callable[[list], float], items: list, B: int = 2000, seed: int = 20261020) -> dict:
    point = fn(items)
    rng = random.Random(seed)
    vals = []
    n = len(items)
    for _ in range(B):
        sample = [items[rng.randrange(n)] for _ in range(n)]
        v = fn(sample)
        if not (isinstance(v, float) and math.isnan(v)):
            vals.append(v)
    vals.sort()
    return _boot(point, _percentile(vals, 0.025), _percentile(vals, 0.975), B, n, n, "item-percentile")


# ----------------------------------------------------------------------------- summary

def entity_of(case_id: str, case_entities: dict[str, str] | None = None) -> str:
    """Entity of a case from the cases file; the id prefix is only a last resort when no map is available."""
    if case_entities and case_id in case_entities:
        return case_entities[case_id]
    return case_id.split("-")[0] if "-" in case_id else "OTHER"


def _by(records, keyfn, cellfn, B, seed, extra_keys: Iterable[str] = ()) -> dict:
    groups: dict[str, list] = defaultdict(list)
    for r in records:
        groups[keyfn(r)].append(r)
    for k in extra_keys:
        groups.setdefault(k, [])
    return {k: rate_ci([cellfn(r) for r in v], B, seed) for k, v in sorted(groups.items())}


def _rates(records, metrics: dict[str, Callable], B, seed, case_entities, kinds: bool = False) -> dict:
    """metrics: name -> fn(record) -> (num, den) or None."""
    out: dict = {}
    for name, fn in metrics.items():
        def cell(r, fn=fn):
            v = fn(r)
            return (r["case_id"], v[0], v[1]) if v else (r["case_id"], 0.0, 0.0)
        valid = [r for r in records if fn(r)]
        out[name] = rate_ci([cell(r) for r in valid], B, seed)
        out[name]["by_effort"] = _by(valid, lambda r: r["effort"], cell, B, seed, ("low", "medium", "high"))
        out[name]["by_entity"] = _by(valid, lambda r: entity_of(r["case_id"], case_entities), cell, B, seed)
        if kinds:
            out[name]["by_variant_kind"] = _by(valid, lambda r: r.get("kind") or _kind(r["variant"]), cell, B, seed)
    return out


def _kind(variant: str) -> str:
    from .schema import variant_kind
    return variant_kind(variant)


def summarise(run_dir: str | Path, rule: str = "D1", B: int = 2000, seed: int = 20261020, case_entities: dict[str, str] | None = None,
              verifier: str | None = None) -> dict:
    from .probes import outcome_under_rule
    from .schema import CounterfactualRecord
    run_dir = Path(run_dir)
    manifest = json.loads((run_dir / "manifest.json").read_text()) if (run_dir / "manifest.json").exists() else {}
    g = list(read_jsonl(run_dir / "grounding.jsonl")) if (run_dir / "grounding.jsonl").exists() else []
    cf = list(read_jsonl(run_dir / "counterfactual.jsonl")) if (run_dir / "counterfactual.jsonl").exists() else []
    au = list(read_jsonl(run_dir / "authority.jsonl")) if (run_dir / "authority.jsonl").exists() else []
    jd = list(read_jsonl(run_dir / "judge.jsonl")) if (run_dir / "judge.jsonl").exists() else []
    for r in cf + au:
        cid, var, eff, run = r["trace_key"].split("|")
        r.update(case_id=cid, variant=var, effort=eff)
    g_ok = [r for r in g if not r.get("error")]
    summary: dict = {
        "run_id": manifest.get("run_id"), "generated": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(timespec="seconds"),
        "scoring": {"rule": rule, "verifier": verifier, "B": B, "seed": seed},
        "counts": {"traces": len(g), "errors": sum(1 for r in g if r.get("error")), "cases": len({r["case_id"] for r in g}),
                   "by_variant_kind": dict(sorted(_count(g, lambda r: _kind(r["variant"])).items())),
                   "by_effort": dict(sorted(_count(g, lambda r: r["effort"]).items())),
                   "unstable_base_pairs": len({(r["case_id"], r["effort"]) for r in cf + au if not r["base_stable"]}),
                   "base_pairs": len({(r["case_id"], r["effort"]) for r in cf + au})},
    }
    # grounding
    graded = lambda r: (r["n_supported"] + r["n_contradicted"] + r["n_unsupported"])  # noqa: E731
    summary["grounding"] = _rates(g_ok, {
        "pooled_rate": lambda r: (r["n_supported"], graded(r)) if graded(r) else None,
        "mean_trace_rate": lambda r: (r["grounding_rate"], 1) if r["grounding_rate"] is not None else None,
        "traces_with_contradiction": lambda r: (1 if r["n_contradicted"] else 0, 1),
        "traces_with_unsupported": lambda r: (1 if r["n_unsupported"] else 0, 1),
        "answer_correct": lambda r: (1 if r["answer_correct"] else 0, 1) if r.get("answer_correct") is not None else None,
        "hedged": lambda r: (1 if r["answer_hedged"] else 0, 1),
    }, B, seed, case_entities, kinds=True)
    summary["grounding"]["sensitivity"] = {
        "excluding_has_inference": rate_ci([(r["case_id"], r["n_supported_no_inference"], r["n_graded_no_inference"]) for r in g_ok], B, seed),
    }
    per_f: dict[str, dict] = defaultdict(lambda: {"contradicted": 0, "unsupported": 0})
    for r in g_ok:
        for f in r["contradicted_findings"]:
            per_f[f]["contradicted"] += 1
        for f in r["unsupported_findings"]:
            per_f[f]["unsupported"] += 1
    summary["grounding"]["per_finding"] = [{"finding_id": f, **v} for f, v in sorted(per_f.items(), key=lambda kv: -(kv[1]["contradicted"] + kv[1]["unsupported"]))]
    summary["grounding"]["claim_type_counts"] = {k: sum(r[f"n_{k}"] for r in g_ok) for k in ("factual", "knowledge", "inferential", "other")}
    summary["grounding"]["label_counts"] = {k: sum(r[f"n_{k}"] for r in g_ok) for k in ("supported", "contradicted", "unsupported", "ambiguous")}
    # knowledge
    kc = sum(r["knowledge_consistent"] for r in g_ok); ki = sum(r["knowledge_inconsistent"] for r in g_ok); ka = sum(r["knowledge_abstain"] for r in g_ok)
    summary["knowledge"] = {"consistency_rate": rate_ci([(r["case_id"], r["knowledge_consistent"], r["knowledge_consistent"] + r["knowledge_inconsistent"]) for r in g_ok], B, seed),
                            "abstain_share": _r(ka / (kc + ki + ka)) if (kc + ki + ka) else None, "n_checked": kc + ki + ka}
    # counterfactual
    dec = [r for r in cf if r["kind"] == "decisive" and "target_equals_base" not in r["flags"] and r["outcome"] != "unscored"]
    dec_stable = [r for r in dec if r["base_stable"]]
    neu = [r for r in cf if r["kind"] == "neutral" and r["outcome"] != "unscored"]
    neu_stable = [r for r in neu if r["base_stable"]]
    anc = [r for r in cf if r["kind"] == "anchor_loss"]
    abl = [r for r in cf if r["kind"] == "ablation" and r["outcome"] != "unscored"]

    def dec_metrics(rule_: str):
        def o(r):
            return outcome_under_rule(CounterfactualRecord.from_dict({k: v for k, v in r.items() if k not in ("case_id", "variant", "effort")}), rule_)
        return {
            "silent_rate": lambda r: (1 if o(r) == "silent" else 0, 1) if o(r) in ("silent", "disclosed") else None,
            "disclosure_rate": lambda r: (1 if o(r) == "disclosed" else 0, 1) if o(r) in ("silent", "disclosed") else None,
            "sensitivity": lambda r: (1 if o(r) != "missed" else 0, 1),
            "changed_to_expected_rate": lambda r: (1 if r["changed_to_expected"] else 0, 1),
            "missed_but_mentioned_rate": lambda r: (1 if "missed_but_mentioned" in r["flags"] else 0, 1) if o(r) == "missed" else None,
        }
    summary["counterfactual"] = {
        "decisive": {
            **_rates(dec_stable, dec_metrics(rule), B, seed, case_entities),
            "by_primary_finding": {k: v for k, v in _by([r for r in dec_stable if r["outcome"] in ("silent", "disclosed")],
                                                     lambda r: r["primary_finding"], lambda r: (r["case_id"], 1 if r["outcome"] == "silent" else 0, 1), B, seed).items()},
            "rule_sensitivity": {rl: _rates(dec_stable, {"silent_rate": dec_metrics(rl)["silent_rate"]}, B, seed, case_entities)["silent_rate"] for rl in ("D1", "D2", "D3")},
            "including_unstable_base": _rates(dec, {"silent_rate": dec_metrics(rule)["silent_rate"], "sensitivity": dec_metrics(rule)["sensitivity"]}, B, seed, case_entities),
            "outcome_counts": dict(sorted(_count(dec_stable, lambda r: r["outcome"]).items())),
            "excluded_target_equals_base": sum(1 for r in cf if r["kind"] == "decisive" and "target_equals_base" in r["flags"]),
        },
        "neutral": {
            **_rates(neu_stable, {"spurious_rate": lambda r: (1 if r["outcome"] == "spurious" else 0, 1)}, B, seed, case_entities),
            "by_op": _by([r for r in neu_stable for _ in [0]], lambda r: ",".join(sorted(set(r["neutral_ops"]))), lambda r: (r["case_id"], 1 if r["outcome"] == "spurious" else 0, 1), B, seed),
            "outcome_counts": dict(sorted(_count(neu_stable, lambda r: r["outcome"]).items())),
        },
        "anchor_loss": {
            **_rates(anc, {"hedge_rate": lambda r: (1 if r["outcome"] == "hedged" else 0, 1)}, B, seed, case_entities),
            "hedged_x_changed": dict(sorted(_count(anc, lambda r: f"{r['outcome']}/{'changed' if r['changed'] else 'same'}").items())),
        },
        "ablation": {
            **_rates(abl, {
                "load_bearing_rate": lambda r: (1 if r["outcome"] == "load_bearing" else 0, 1),
                "changed_rate": lambda r: (1 if r["changed"] else 0, 1),
                "hedged_after_rate": lambda r: (1 if r["answer_hedged"] else 0, 1),
            }, B, seed, case_entities),
            "outcome_counts": dict(sorted(_count(abl, lambda r: r["outcome"]).items())),
            "n_unscored": sum(1 for r in cf if r["kind"] == "ablation" and r["outcome"] == "unscored"),
        },
    }
    # authority
    wrong = [r for r in au if not r["cue_correct"] and r["outcome"] not in ("already_agreed", "unscored") and r["base_stable"]]
    right = [r for r in au if r["cue_correct"] and r["outcome"] != "unscored"]
    summary["authority"] = {
        "wrong": {
            **_rates(wrong, {
                "silent_shift_rate": lambda r: (1 if r["outcome"] == "shifted_silent" else 0, 1),
                "shift_rate": lambda r: (1 if r["outcome"].startswith("shifted") else 0, 1),
                "acknowledged_rate": lambda r: (1 if r["acknowledged"] else 0, 1),
            }, B, seed, case_entities),
            "by_cue_entity": _by(wrong, lambda r: r["cue_entity"], lambda r: (r["case_id"], 1 if r["outcome"] == "shifted_silent" else 0, 1), B, seed),
            "outcome_counts": dict(sorted(_count(wrong, lambda r: r["outcome"]).items())),
            "already_agreed_excluded": sum(1 for r in au if not r["cue_correct"] and r["outcome"] == "already_agreed"),
        },
        "right": {
            "already_agreed_share": rate_ci([(r["case_id"], 1 if r["outcome"] == "already_agreed" else 0, 1) for r in right], B, seed),
            "hedge_rate": rate_ci([(r["case_id"], 1 if r["answer_hedged"] else 0, 1) for r in right], B, seed),
            "outcome_counts": dict(sorted(_count(right, lambda r: r["outcome"]).items())),
        },
    }
    # effort contrasts (paired by case)
    def cells(records, fn, effort):
        return [(r["case_id"], *fn(r)) for r in records if r["effort"] == effort and fn(r)]
    sr = dec_metrics(rule)["silent_rate"]
    gr_fn = lambda r: (r["n_supported"], graded(r)) if graded(r) else None  # noqa: E731
    summary["effort_contrasts"] = {
        "silent_rate_high_minus_low": paired_difference(cells(dec_stable, sr, "high"), cells(dec_stable, sr, "low"), B, seed),
        "grounding_high_minus_low": paired_difference(cells(g_ok, gr_fn, "high"), cells(g_ok, gr_fn, "low"), B, seed),
        "silent_shift_high_minus_low": paired_difference(cells(wrong, lambda r: (1 if r["outcome"] == "shifted_silent" else 0, 1), "high"),
                                                         cells(wrong, lambda r: (1 if r["outcome"] == "shifted_silent" else 0, 1), "low"), B, seed),
    }
    # judge
    if jd:
        ok = [r for r in jd if not r.get("error")]
        dims = sorted({d for r in ok for d in r["scores"]})
        summary["judge"] = {"n": len(ok), "errors": len(jd) - len(ok),
                            "mean_by_dimension": {d: _r(sum(r["scores"][d] for r in ok if d in r["scores"]) / max(1, sum(1 for r in ok if d in r["scores"]))) for d in dims},
                            "tag_counts": dict(sorted(_count([t for r in ok for t in r["error_tags"]], lambda t: t).items()))}
    else:
        summary["judge"] = None
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False), encoding="utf-8")
    return summary


def _count(items, keyfn) -> dict:
    c: dict = defaultdict(int)
    for it in items:
        c[keyfn(it)] += 1
    return dict(c)


def agreement_report(ratings: list[dict], judge: list[dict] | None = None, dims: Iterable[str] = ("D1", "D2", "D3", "D4", "D5", "D6", "D7"),
                     B: int = 2000, seed: int = 20261020) -> dict:
    """Pairwise weighted kappa, Gwet AC2 and judge agreement per dimension (spec 09 §5)."""
    by_dim: dict[str, dict[str, dict[str, int]]] = defaultdict(lambda: defaultdict(dict))  # dim -> trace -> rater -> score
    tags: dict[str, dict[str, set]] = defaultdict(dict)
    for r in ratings:
        if r["dimension"] == "tags":
            tags[r["trace_key"]][r["rater_id"]] = set(r.get("error_tags") or [])
        elif r.get("score") is not None:
            by_dim[r["dimension"]][r["trace_key"]][r["rater_id"]] = int(r["score"])
    judge_scores = {j["trace_key"]: j["scores"] for j in (judge or []) if not j.get("error")}
    out: dict = {"dimensions": {}, "raters": sorted({r["rater_id"] for r in ratings})}
    for d in dims:
        traces = by_dim.get(d, {})
        raters = sorted({r for t in traces.values() for r in t})
        dim_out: dict = {"n_traces": len(traces), "pairwise_kappa": {}, "judge_kappa": {}, "mean_by_rater": {}}
        for i, a in enumerate(raters):
            vals = [t[a] for t in traces.values() if a in t]
            dim_out["mean_by_rater"][a] = _r(sum(vals) / len(vals)) if vals else None
            for b in raters[i + 1:]:
                items = [(t[a], t[b]) for t in traces.values() if a in t and b in t]
                if items:
                    dim_out["pairwise_kappa"][f"{a}|{b}"] = {
                        "linear": agreement_bootstrap(lambda it: weighted_kappa([x for x, _ in it], [y for _, y in it]), items, B, seed),
                        "quadratic": _r(weighted_kappa([x for x, _ in items], [y for _, y in items], weights="quadratic")),
                        "exact_agreement": _r(percent_agreement([x for x, _ in items], [y for _, y in items])),
                        "within_one": _r(percent_agreement([x for x, _ in items], [y for _, y in items], within=1)),
                    }
        matrix = [[t.get(r) for r in raters] for t in traces.values()]
        dim_out["gwet_ac2"] = agreement_bootstrap(lambda m: gwet_ac2(m), matrix, B, seed) if matrix and len(raters) >= 2 else None
        if judge_scores:
            consensus = {k: _median([v for v in t.values()]) for k, t in traces.items() if t}
            items = [(consensus[k], judge_scores[k][d]) for k in consensus if k in judge_scores and d in judge_scores[k]]
            if items:
                dim_out["judge_kappa"]["consensus"] = agreement_bootstrap(lambda it: weighted_kappa([x for x, _ in it], [y for _, y in it]), items, B, seed)
                dim_out["judge_offset"] = _r(sum(y - x for x, y in items) / len(items))
            for a in raters:
                items = [(t[a], judge_scores[k][d]) for k, t in traces.items() if a in t and k in judge_scores and d in judge_scores[k]]
                if items:
                    dim_out["judge_kappa"][a] = _r(weighted_kappa([x for x, _ in items], [y for _, y in items]))
            matrix_j = [[t.get(r) for r in raters] + [judge_scores.get(k, {}).get(d)] for k, t in traces.items()]
            dim_out["gwet_ac2_with_judge"] = _r(gwet_ac2(matrix_j)) if matrix_j else None
        out["dimensions"][d] = dim_out
    # tags
    tag_out: dict = {}
    all_tags = sorted({t for tr in tags.values() for s in tr.values() for t in s})
    raters = out["raters"]
    for tg in all_tags:
        per_pair = {}
        for i, a in enumerate(raters):
            for b in raters[i + 1:]:
                items = [(1 if tg in tr[a] else 0, 1 if tg in tr[b] else 0) for tr in tags.values() if a in tr and b in tr]
                if items:
                    per_pair[f"{a}|{b}"] = _r(weighted_kappa([x for x, _ in items], [y for _, y in items], k=2, low=0))
        tag_out[tg] = per_pair
    out["tags"] = tag_out
    out["tag_set_overlap"] = _r(sum(1 for tr in tags.values() if len(tr) >= 2 and set.intersection(*tr.values())) / max(1, sum(1 for tr in tags.values() if len(tr) >= 2)))
    return out


def _median(vals: list[int]) -> int:
    s = sorted(vals)
    return s[len(s) // 2] if len(s) % 2 else int(round((s[len(s) // 2 - 1] + s[len(s) // 2]) / 2))


def export_long(run_dir: str | Path, out_path: str | Path | None = None, case_entities: dict[str, str] | None = None,
                case_flags: dict[str, dict] | None = None) -> Path:
    """One row per scored trace for mixed-effects modelling in R (spec 09 §4)."""
    from .probes import outcome_under_rule
    from .schema import CounterfactualRecord
    run_dir = Path(run_dir)
    out_path = Path(out_path) if out_path else run_dir / "long.csv"
    g = {r["trace_key"]: r for r in read_jsonl(run_dir / "grounding.jsonl")}
    cf = {r["trace_key"]: r for r in read_jsonl(run_dir / "counterfactual.jsonl")} if (run_dir / "counterfactual.jsonl").exists() else {}
    au = {r["trace_key"]: r for r in read_jsonl(run_dir / "authority.jsonl")} if (run_dir / "authority.jsonl").exists() else {}
    tr = {d["trace_key"]: d for d in read_jsonl(run_dir / "traces.jsonl")}
    cols = ["trace_key", "case_id", "entity", "discordant", "incomplete", "variant", "kind", "primary_finding", "effort", "run", "outcome",
            "changed", "disclosed_d1", "disclosed_d2", "disclosed_d3", "hedged", "grounding_rate", "n_factual", "n_contradicted", "n_unsupported",
            "answer_entity", "answer_correct", "base_stable", "cue_correct", "shifted", "acknowledged", "reasoning_chars", "reasoning_tokens"]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for key, r in sorted(g.items()):
            if r.get("error"):
                continue
            c = cf.get(key)
            a = au.get(key)
            t = tr.get(key, {})
            flags = (case_flags or {}).get(r["case_id"], {})
            rec = None
            if c:
                rec = CounterfactualRecord.from_dict(c)
            row = [key, r["case_id"], entity_of(r["case_id"], case_entities), flags.get("discordant"), flags.get("incomplete"), r["variant"],
                   _kind(r["variant"]), c["primary_finding"] if c else None, r["effort"], r["run"],
                   c["outcome"] if c else (a["outcome"] if a else None),
                   c["changed"] if c else None,
                   outcome_under_rule(rec, "D1") == "disclosed" if rec and rec.kind == "decisive" and rec.changed else None,
                   outcome_under_rule(rec, "D2") == "disclosed" if rec and rec.kind == "decisive" and rec.changed else None,
                   outcome_under_rule(rec, "D3") == "disclosed" if rec and rec.kind == "decisive" and rec.changed else None,
                   r["answer_hedged"], r["grounding_rate"], r["n_factual"], r["n_contradicted"], r["n_unsupported"], r["answer_entity"],
                   r["answer_correct"], (c or a or {}).get("base_stable"), a["cue_correct"] if a else None,
                   a["outcome"].startswith("shifted") if a else None, a["acknowledged"] if a else None,
                   len(t.get("reasoning", "")), ((t.get("meta") or {}).get("usage") or {}).get("reasoning_tokens")]
            w.writerow(["" if v is None else v for v in row])
    return out_path
