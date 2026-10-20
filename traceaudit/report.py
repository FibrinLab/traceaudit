"""Markdown rendering of summary.json."""
from __future__ import annotations


def _ci(x: dict | None) -> str:
    if not x or x.get("point") is None:
        return "—"
    lo, hi = x.get("lo"), x.get("hi")
    n = x.get("denominator")
    s = f"{x['point']:.3f}"
    if lo is not None and hi is not None:
        s += f" [{lo:.3f}, {hi:.3f}]"
    if n is not None:
        s += f" (n={int(n)})"
    return s


def render_markdown(s: dict) -> str:
    out = [f"# traceaudit summary — run {s.get('run_id')}", "", f"Generated {s.get('generated')}; disclosure rule {s['scoring']['rule']}; verifier {s['scoring']['verifier']}; B={s['scoring']['B']}", ""]
    c = s["counts"]
    out += ["## Counts", "", f"- traces: {c['traces']} (errors {c['errors']}), cases {c['cases']}", f"- by variant kind: {c['by_variant_kind']}",
            f"- unstable base pairs: {c['unstable_base_pairs']} / {c['base_pairs']}", ""]
    g = s["grounding"]
    out += ["## RQ1 Grounding", "", "| Metric | Overall | low | medium | high |", "|---|---|---|---|---|"]
    for name in ("pooled_rate", "mean_trace_rate", "traces_with_contradiction", "traces_with_unsupported", "answer_correct", "hedged"):
        m = g[name]
        out.append(f"| {name} | {_ci(m)} | {_ci(m['by_effort'].get('low'))} | {_ci(m['by_effort'].get('medium'))} | {_ci(m['by_effort'].get('high'))} |")
    out.append(f"| excluding has_inference | {_ci(g['sensitivity']['excluding_has_inference'])} | | | |")
    out += ["", f"Claim types: {g['claim_type_counts']}; labels: {g['label_counts']}", ""]
    if g["per_finding"]:
        out += ["Top findings by contradiction + fabrication:", ""] + [f"- {r['finding_id']}: contradicted {r['contradicted']}, unsupported {r['unsupported']}" for r in g["per_finding"][:8]] + [""]
    d = s["counterfactual"]["decisive"]
    out += ["## RQ2 Counterfactual (decisive, stable base)", "", "| Metric | Overall | low | medium | high |", "|---|---|---|---|---|"]
    for name in ("silent_rate", "disclosure_rate", "sensitivity", "changed_to_expected_rate"):
        m = d[name]
        out.append(f"| {name} | {_ci(m)} | {_ci(m['by_effort'].get('low'))} | {_ci(m['by_effort'].get('medium'))} | {_ci(m['by_effort'].get('high'))} |")
    out += ["", f"Outcomes: {d['outcome_counts']}; excluded target_equals_base: {d['excluded_target_equals_base']}",
            f"Rule sensitivity (silent rate): D1 {_ci(d['rule_sensitivity']['D1'])}, D2 {_ci(d['rule_sensitivity']['D2'])}, D3 {_ci(d['rule_sensitivity']['D3'])}", ""]
    n = s["counterfactual"]["neutral"]
    out += [f"Neutral spurious rate: {_ci(n['spurious_rate'])}; outcomes {n['outcome_counts']}",
            f"Anchor-loss hedge rate: {_ci(s['counterfactual']['anchor_loss']['hedge_rate'])}; hedged×changed {s['counterfactual']['anchor_loss']['hedged_x_changed']}", ""]
    a = s["authority"]
    out += ["## RQ3 Authority (wrong cue, base ≠ cue, stable base)", "", "| Metric | Overall | low | medium | high |", "|---|---|---|---|---|"]
    for name in ("silent_shift_rate", "shift_rate", "acknowledged_rate"):
        m = a["wrong"][name]
        out.append(f"| {name} | {_ci(m)} | {_ci(m['by_effort'].get('low'))} | {_ci(m['by_effort'].get('medium'))} | {_ci(m['by_effort'].get('high'))} |")
    out += ["", f"Wrong-cue outcomes: {a['wrong']['outcome_counts']}; right-cue outcomes: {a['right']['outcome_counts']}; right-cue hedge rate {_ci(a['right']['hedge_rate'])}", ""]
    k = s["knowledge"]
    out += ["## Knowledge consistency (exploratory)", "", f"consistency {_ci(k['consistency_rate'])}; abstain share {k['abstain_share']}; checked {k['n_checked']}", ""]
    e = s["effort_contrasts"]
    out += ["## RQ5 Effort contrasts (high − low, paired by case)", ""] + [f"- {name}: {_ci(v)}" for name, v in e.items()] + [""]
    if s.get("judge"):
        out += ["## Judge", "", f"n={s['judge']['n']} (errors {s['judge']['errors']}); mean by dimension {s['judge']['mean_by_dimension']}; tags {s['judge']['tag_counts']}", ""]
    return "\n".join(out)
