"""Command-line interface (spec 08 §5)."""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

from . import __version__
from . import lexicon as lex_mod

from .domains import sample_paths as _sample_paths

SAMPLE_CASES, SAMPLE_PERTS = _sample_paths("haematology")


def _err(msg: str, code: int = 1) -> int:
    print(f"error: {msg}", file=sys.stderr)
    return code


def _progress(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def cmd_validate(a) -> int:
    from .schema import load_cases, load_perturbations, validate_case, validate_perturbation
    lx = lex_mod.load(a.lexicon)
    cases = load_cases(a.cases)
    probs = []
    for c in cases:
        probs += validate_case(c, lx)
    if a.perturbations:
        by_id = {c.case_id: c for c in cases}
        for p in load_perturbations(a.perturbations):
            probs += validate_perturbation(p, by_id.get(p.case_id), lx)
    for p in probs:
        print(p)
    errors = [p for p in probs if p.severity == "error"]
    print(f"{len(cases)} cases checked; {len(errors)} errors, {len(probs) - len(errors)} warnings")
    return 1 if errors else 0


def cmd_perturb(a) -> int:
    from . import perturb
    from .schema import load_cases, load_perturbations, write_jsonl
    lx = lex_mod.load(a.lexicon)
    cases = load_cases(a.cases)
    out = []
    for c in cases:
        out += perturb.generate_all(c, a.seed, lx)
    if a.merge_review and Path(a.out).exists():
        out = perturb.merge_review(out, load_perturbations(a.out))
    if a.approve_all:
        from .schema import Review
        for p in out:
            p.review = Review("R00", "1970-01-01", "approved", "auto-approved (--approve-all)")
    write_jsonl(a.out, out)
    for line in perturb.generation_log():
        print("skipped:", line, file=sys.stderr)
    print(f"wrote {len(out)} perturbations to {a.out}")
    return 0


def cmd_casegen(a) -> int:
    from .domains.haematology import casegen
    from .schema import write_jsonl
    lx = lex_mod.load(a.lexicon or Path(casegen.__file__).with_name("lexicon.json"))
    priors = casegen.load_priors(a.priors)
    cases = casegen.generate_set(a.per_entity, a.seed, lx, priors, a.entities.split(",") if a.entities else None)
    if a.approve_all:
        casegen.approve_all(cases)
    write_jsonl(a.out, cases)
    n_disc = sum(c.flags.discordant for c in cases)
    n_inc = sum(c.flags.incomplete for c in cases)
    print(f"wrote {len(cases)} cases to {a.out} (discordant {n_disc}, incomplete {n_inc})")
    return 0


def cmd_review_sheet(a) -> int:
    from .domains.haematology import casegen
    from .schema import load_cases, write_jsonl
    cases = load_cases(a.cases)
    if a.import_csv:
        cases = casegen.import_review_sheet(cases, Path(a.import_csv).read_text(encoding="utf-8"), a.reviewer, a.date)
        write_jsonl(a.cases, cases)
        print(f"review imported for {len(cases)} cases")
    else:
        Path(a.out).write_text(casegen.review_sheet(cases), encoding="utf-8")
        print(f"review sheet written to {a.out}")
    return 0


def _client(a):
    from .clients import make_client
    kw = {}
    if a.client == "sim":
        from .simulate import SimParams
        # --sim-p sets every fault rate except base noise and trace/answer mismatch, which make planted rates unidentifiable
        params = SimParams.uniform(a.sim_p, p_base_noise=0.0, p_trace_answer_mismatch=0.0) if a.sim_p is not None else SimParams()
        if a.sim_params:
            params = SimParams(**{**params.__dict__, **json.loads(a.sim_params)})
        kw = {"params": params, "seed": a.seed}
    return make_client(a.client, a.model, a.endpoint, **kw)


def cmd_run(a) -> int:
    from . import experiment
    from .schema import load_cases, load_perturbations
    lx = lex_mod.load(a.lexicon)
    cases = load_cases(a.cases)
    perts = load_perturbations(a.perturbations) if a.perturbations else []
    efforts = a.efforts.split(",")
    client = _client(a)
    try:
        prompt = experiment.load_prompt(a.prompt)
    except OSError:
        return _err(f"prompt {a.prompt!r} not found", 2)
    run_dir = Path(a.out)
    jobs = experiment.plan(cases, perts, efforts, a.runs, a.seed, a.cases_filter.split(",") if a.cases_filter else None,
                           a.entities.split(",") if a.entities else None, a.variants.split(",") if a.variants else None,
                           a.allow_unreviewed, lx)
    if not jobs:
        return _err("no jobs planned (are the cases approved? use --allow-unreviewed for drafts)")
    if (run_dir / "manifest.json").exists() and not a.force:
        manifest = experiment.read_manifest(run_dir)
        manifest["status"] = "running"
    else:
        try:
            desc_ok = client.describe()
        except Exception as e:  # noqa: BLE001
            return _err(f"client unreachable: {e}", 4)
        if desc_ok.get("describe_error") and a.client != "sim":
            print(f"warning: describe() incomplete: {desc_ok['describe_error']}", file=sys.stderr)
        sampling = {"temperature": a.temperature, "top_p": 1.0, "max_tokens": a.max_tokens, "timeout_s": a.timeout}
        from .schema import RUN_ID_RE
        run_id = run_dir.name if RUN_ID_RE.match(run_dir.name) else experiment.new_run_id(random.Random(a.seed))
        manifest = experiment.build_manifest(run_id, client, prompt, efforts, a.runs, a.seed, a.cases, a.perturbations, lx, len(cases), len(perts),
                                             {"cases": a.cases_filter, "entities": a.entities, "variants": a.variants, "allow_unreviewed": a.allow_unreviewed},
                                             sampling, a.workers, a.notes or "", a.allow_dirty)
        if manifest.get("git_dirty") and not a.allow_dirty and a.client != "sim":
            print("warning: git tree is dirty; pass --allow-dirty 'reason' to record a justification", file=sys.stderr)
    print(f"planned {len(jobs)} jobs -> {run_dir}", file=sys.stderr)
    try:
        counts = experiment.run_experiment(jobs, client, run_dir, manifest, prompt, a.seed, a.workers, a.redo_errors, a.force, a.min_interval_ms,
                                           progress=_progress if not a.quiet else None,
                                           sampling={"temperature": a.temperature, "max_tokens": a.max_tokens, "timeout_s": a.timeout})
    except experiment.ModelChanged as e:
        return _err(str(e), 3)
    print(json.dumps(counts))
    return 0


def _inputs(a):
    from .pipeline import resolve_inputs
    return resolve_inputs(a.run_dir, a.cases, a.perturbations)


def cmd_ground(a) -> int:
    from .pipeline import ground_run
    lx = lex_mod.load(a.lexicon)
    cases, perts = _inputs(a)
    print(json.dumps(ground_run(a.run_dir, cases, perts, None if a.verify == "none" else a.verify, lx, progress=_progress)))
    return 0


def cmd_score(a) -> int:
    from .pipeline import score_all
    lx = lex_mod.load(a.lexicon)
    cases, perts = _inputs(a)
    out = score_all(a.run_dir, cases, perts, a.rule, None if a.verify == "none" else a.verify, a.B, a.seed, lx, progress=_progress)
    if a.judge:
        from . import judge as judge_mod
        from .clients import make_client
        client = make_client(a.judge_client, a.judge_model, a.judge_endpoint) if a.judge_client != "sim" else _sim_judge(a.seed)
        keys = None
        if a.judge_keys:
            keys = set(Path(a.judge_keys).read_text().split())
        n = judge_mod.run_judge(a.run_dir, cases, perts, client, a.judge_model, keys, lx, progress=_progress)
        from .experiment import append_scoring
        append_scoring(a.run_dir, "judge", {"judge_model": a.judge_model, "prompt_sha256": judge_mod.prompt_sha256(), "n": n})
        from . import stats
        stats.summarise(a.run_dir, a.rule, a.B, a.seed, {c.case_id: c.entity for c in cases}, a.verify)
    s = out["summary"]
    print(json.dumps({"traces": s["counts"]["traces"], "grounding_rate": s["grounding"]["pooled_rate"]["point"],
                      "silent_rate": s["counterfactual"]["decisive"]["silent_rate"]["point"],
                      "spurious_rate": s["counterfactual"]["neutral"]["spurious_rate"]["point"],
                      "silent_shift_rate_wrong": s["authority"]["wrong"]["silent_shift_rate"]["point"]}))
    return 0


def _sim_judge(seed: int):
    """A deterministic fake judge for demos/tests: scores derived from text length; never used in a study."""
    from .clients.callable_ import CallableClient
    import zlib

    def fn(system, user, effort, seed_, **kw):
        h = zlib.crc32(user.encode())
        rng = random.Random(h ^ seed)
        scores = {d: rng.randint(2, 4) for d in ("D1", "D2", "D3", "D4", "D5", "D6", "D7")}
        tags = ["none"] if rng.random() < 0.6 else [rng.choice(["ignored_finding", "overconfidence", "logical_leap"])]
        return {"reasoning": "", "answer": json.dumps({"scores": scores, "error_tags": tags, "rationale": {}, "overall_comment": "simulated judge"})}
    return CallableClient(fn, name="simulated-judge")


def cmd_report(a) -> int:
    from .report import render_markdown
    s = json.loads((Path(a.run_dir) / "summary.json").read_text())
    if a.format == "json":
        print(json.dumps(s, indent=1))
    else:
        print(render_markdown(s))
    return 0


def cmd_export(a) -> int:
    from . import export
    from .schema import read_jsonl
    lx = lex_mod.load(a.lexicon)
    cases, perts = _inputs(a)
    study = None
    if a.study_id:
        keys = export.select_rating_set(Path(a.run_dir) / "grounding.jsonl", a.rating_n, a.seed, {c.case_id: c.entity for c in cases})
        study = {"study_id": a.study_id, "rating_set": keys, "blinding_seed": a.seed}
    ratings = None
    if a.ratings:
        ratings = []
        for p in Path(a.ratings).glob("**/*.jsonl"):
            ratings += list(read_jsonl(p))
    viewer = Path(a.with_viewer) if a.with_viewer else None
    out = export.to_viewer(a.run_dir, a.out, cases, perts, shard=not a.single, include_raw=a.include_raw, study=study, lexicon=lx,
                           redact_prompt=a.redact_prompt, ratings=ratings, with_viewer=viewer)
    print(f"bundle written to {out}")
    return 0


def cmd_import_ratings(a) -> int:
    from .export import import_ratings
    n, probs = import_ratings(a.file, a.dest, a.allow_unblinded)
    for p in probs:
        print(p, file=sys.stderr)
    print(f"imported {n} ratings ({len(probs)} rejected)")
    return 1 if probs and n == 0 else 0


def cmd_agreement(a) -> int:
    from . import stats
    from .schema import read_jsonl
    ratings = []
    for p in Path(a.ratings).glob("**/*.jsonl"):
        ratings += list(read_jsonl(p))
    judge = list(read_jsonl(a.judge)) if a.judge else None
    print(json.dumps(stats.agreement_report(ratings, judge, B=a.B), indent=1))
    return 0


def cmd_demo(a) -> int:
    """SimulatedModel end-to-end on the packaged sample."""
    import argparse as _ap
    out = Path(a.out)
    ns = _ap.Namespace(client="sim", model="simulated", endpoint=None, sim_p=a.sim_p, sim_params=None, seed=a.seed, lexicon=None,
                       cases=str(SAMPLE_CASES), perturbations=str(SAMPLE_PERTS), efforts="low,medium,high", runs=a.runs, out=str(out),
                       cases_filter=None, entities=None, variants=None, allow_unreviewed=False, prompt="enable-v3", workers=1,
                       redo_errors=False, force=True, min_interval_ms=0, temperature=1.0, max_tokens=8192, timeout=600.0, notes="demo",
                       allow_dirty="demo", quiet=True)
    rc = cmd_run(ns)
    if rc:
        return rc
    ns2 = _ap.Namespace(run_dir=str(out), cases=str(SAMPLE_CASES), perturbations=str(SAMPLE_PERTS), lexicon=None, rule="D1", verify="lexical",
                        B=a.B, seed=a.seed, judge=a.judge, judge_client="sim", judge_model="simulated-judge", judge_endpoint=None, judge_keys=None)
    rc = cmd_score(ns2)
    if rc:
        return rc
    ns3 = _ap.Namespace(run_dir=str(out), cases=str(SAMPLE_CASES), perturbations=str(SAMPLE_PERTS), lexicon=None, out=str(out / "export"),
                        single=False, include_raw=False, study_id="demo", rating_n=12, seed=a.seed, ratings=None, with_viewer=a.with_viewer, redact_prompt=False)
    return cmd_export(ns3)


def cmd_validate_probes(a) -> int:
    from .validation import run_grid
    res = run_grid(a.grid, Path(a.out), a.seed, progress=_progress, cases_path=a.cases, perturbations_path=a.perturbations)
    print(res["markdown"])
    return 0 if res["passed"] else 1


def cmd_serve(a) -> int:
    from .serve import ServiceConfig, serve_forever
    import os
    op_keys: dict[str, str] = {}
    specs = list(a.operator_key) or [x for x in (os.environ.get("TRACEAUDIT_OPERATOR_KEYS") or "").split(",") if x.strip()]
    for spec in specs:
        kind, _, env = spec.partition("=")
        val = os.environ.get(env.strip() or "", "")
        if val:
            op_keys[kind.strip()] = val
        else:
            print(f"warning: operator key for {kind.strip()!r}: environment variable {env.strip()!r} is empty", file=sys.stderr)
    cfg = ServiceConfig.from_args(root=a.root, host=a.host, port=a.port, static=a.static,
                                  tokens=a.tokens or os.environ.get("TRACEAUDIT_TOKENS"),
                                  anonymous=a.anonymous or os.environ.get("TRACEAUDIT_ANONYMOUS") or "analyse",
                                  allow_clients=a.allow_clients or os.environ.get("TRACEAUDIT_ALLOW_CLIENTS") or "sim",
                                  rate_per_min=a.rate, extra_cases=a.cases, operator_keys=op_keys,
                                  max_calls_per_job=a.max_calls_per_job or int(os.environ.get("TRACEAUDIT_MAX_CALLS_PER_JOB") or 200),
                                  max_calls_per_day=a.max_calls_per_day or int(os.environ.get("TRACEAUDIT_MAX_CALLS_PER_DAY") or 2000),
                                  domain=a.domain or os.environ.get("TRACEAUDIT_DOMAIN") or None, lexicon=a.default_lexicon,
                                  examples_dir=a.examples or os.environ.get("TRACEAUDIT_EXAMPLES") or None)
    print(f"traceaudit serve on http://{a.host}:{a.port} (root {a.root}, domain {cfg.domain or cfg.lexicon_path or 'none built in'}, clients {sorted(cfg.allow_clients)}, anonymous {cfg.anonymous}, "
          f"site keys for {sorted(cfg.operator_keys) or 'none'}, caps {cfg.max_calls_per_job}/job {cfg.max_calls_per_day}/day)", file=sys.stderr)
    serve_forever(cfg)
    return 0


def cmd_cases(a) -> int:
    from .cases import build_cases, coverage_report
    from .schema import write_jsonl
    lx = lex_mod.load(a.lexicon)
    cases, problems = build_cases(a.documents, lx, approve=a.approve)
    for cid, probs in problems.items():
        for p in probs:
            print(f"{cid}: {p}", file=sys.stderr)
    clean = [c for c in cases if c.case_id not in problems] if a.strict else cases
    write_jsonl(a.out, clean)
    rep = coverage_report(clean, lx)
    print(json.dumps({"written": len(clean), "with_problems": len(problems), "coverage": rep}, indent=1))
    return 1 if (a.strict and problems) else 0


def ledger_artefact_paths(inputs: list[str]) -> list[Path]:
    """Expand files, directories (every *.md inside, recursively) and globs into artefact paths, sorted."""
    import glob
    out: list[Path] = []
    for item in inputs:
        pth = Path(item)
        if pth.is_dir():
            out += sorted(q for q in pth.rglob("*.md") if q.is_file())
        elif pth.exists():
            out.append(pth)
        else:
            out += sorted(Path(q) for q in glob.glob(item, recursive=True))
    seen: set[Path] = set()
    return [q for q in out if not (q in seen or seen.add(q))]


def cmd_ledger_audit(a) -> int:
    import csv
    from . import ledger as ledger_mod
    from .importers import load as load_artefact
    paths = ledger_artefact_paths(a.paths)
    if not paths:
        print("no artefacts found", file=sys.stderr)
        return 2
    results = []
    for pth in paths:
        case, trace = load_artefact(pth)
        res = ledger_mod.audit(case, trace)
        res["source_path"] = str(pth)
        results.append(res)
    if a.review_sheet:
        with open(a.review_sheet, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=ledger_mod.REVIEW_COLUMNS)
            w.writeheader()
            for res in results:
                for row in ledger_mod.review_rows(res):
                    w.writerow({**row, "human_grade": "", "note": ""})
        print(f"review sheet: {a.review_sheet} ({sum(len(ledger_mod.review_rows(r)) for r in results)} rows)", file=sys.stderr)
    many = len(results) > 1 or a.summary
    if a.json:
        print(json.dumps(ledger_mod.audit_many(results) if many else results[0], indent=1))
        return 0
    if not many:
        _print_ledger_result(results[0])
        return 1 if results[0]["metrics"]["checks_failed"] else 0
    agg = ledger_mod.audit_many(results)
    for pc in agg["per_case"]:
        print(f"{pc['case_id']}: decision {pc['decision']} (truth {pc['truth']}); {pc['checks_failed']} of {pc['checks_total']} checks failed")
    print(f"\n{agg['n']} artefact(s); decision matches truth in {agg['decision_matches_truth']['matches']} of {agg['decision_matches_truth']['n']}")
    print("check pass rates:")
    for cid, row in sorted(agg["check_pass_rates"].items(), key=lambda kv: (kv[1]["pass_rate"] or 0, kv[0])):
        print(f"  {row['pass']:3}/{row['n']:<3} {row['title']}")
    g = agg["grade_counts"]
    print("citation grades: " + ", ".join(f"{k} {v}" for k, v in sorted(g["cited"].items())))
    if g["uncited"]:
        print("uncited assertions: " + ", ".join(f"{k} {v}" for k, v in sorted(g["uncited"].items())))
    return 1 if any(pc["checks_failed"] for pc in agg["per_case"]) else 0


def _print_ledger_result(res: dict) -> None:
    print(f"{res['case_id']}: decision {res['decision']} (truth {res['truth']}); {res['metrics']['checks_failed']} of {res['metrics']['checks_total']} checks failed")
    for ch in res["checks"]:
        print(f"  {ch['status']:4} {ch['title']}" + (f" — {ch['detail']}" if ch["detail"] else ""))
    m = res["metrics"]
    print(f"  facts {m['facts']} (patient {m['patient_facts']}, context {m['context_facts']}, reference {m['reference_facts']}); "
          f"cited in report {m['cited_in_report']} (agree {m['cited_agree']}, disagree {m['cited_disagree']}, unverifiable {m['cited_unverifiable']}); "
          f"ignored {m['ignored']} ({m['ignored_informative']} informative)")


def _ledger_client(a):
    from .clients import make_client
    if a.client == "sim":
        from .ledger_sim import LedgerSimParams, LedgerSimulatedModel
        params = LedgerSimParams.uniform(a.sim_p, p_base_noise=0.0, p_trace_answer_mismatch=0.0, p_contract_break=0.0) if a.sim_p is not None else LedgerSimParams()
        if a.sim_params:
            params = LedgerSimParams(**{**params.__dict__, **json.loads(a.sim_params)})
        return LedgerSimulatedModel.client(params, seed=a.seed)
    return make_client(a.client, a.model, a.endpoint)


def _base_lexicon(a):
    return lex_mod.load(a.lexicon) if getattr(a, "lexicon", None) else None


def cmd_ledger_cases(a) -> int:
    from . import ledger_io, ledger_pipeline as PL
    paths = ledger_artefact_paths(a.paths)
    if not paths:
        return _err("no artefacts found", 2)
    cases, problems = PL.cases_from_artefacts(paths)
    for pr in problems:
        print(json.dumps(pr), file=sys.stderr)
    n = ledger_io.write_cases(a.out, cases)
    print(f"wrote {n} case(s) -> {a.out}" + (f"; {len(problems)} problem(s)" if problems else ""), file=sys.stderr)
    return 1 if problems and a.strict else 0


def cmd_ledger_perturb(a) -> int:
    from . import ledger_io, ledger_perturb as LP, ledger_pipeline as PL
    from .schema import load_perturbations, write_jsonl
    cases = ledger_io.load_cases(a.cases)
    lx = _base_lexicon(a)
    sources = tuple(x.strip() for x in a.expectations.split(",") if x.strip())
    rationales_by_case: dict[str, list] = {}
    if a.rationale_from:
        from . import ledger_probes as LPR
        from .schema import load_traces
        rd = Path(a.rationale_from)
        traces = load_traces(rd / "traces.jsonl") if (rd / "traces.jsonl").exists() else []
        views = LPR.build_views(cases, [], lx)
        for t in traces:
            if t.variant == "base" and t.ok and (t.case_id, "base") in views:
                lt, _ = LPR.parse_trace(t, views[(t.case_id, "base")], lx)
                if lt.rationale is not None:
                    rationales_by_case.setdefault(t.case_id, []).append(lt.rationale)
        if not rationales_by_case:
            for pth in ledger_artefact_paths([a.rationale_from]):
                from .importers import parse_markdown
                c, t = parse_markdown(pth.read_text(encoding="utf-8"))
                if t.rationale is not None:
                    rationales_by_case.setdefault(c.case_id, []).append(t.rationale)
        sources = sources + ("rationale",) if "rationale" not in sources else sources
    kinds = tuple(k.strip() for k in a.kinds.split(",") if k.strip())
    kind_map = {"dec": "decisive", "neu": "neutral", "anc": "anchor_loss", "auth": "authority"}
    kinds = tuple(kind_map.get(k, k) for k in kinds)
    out = []
    for c in cases:
        exps = LP.expectations(c, lx, sources, rationales_by_case.get(c.case_id))
        ps = LP.generate_all(c, a.seed, lx, exps, kinds, True if a.include_right else None, a.max_flips, a.max_decisive, a.anchor_op)
        if a.approve_all:
            for p in ps:
                p.review.status = "approved"
        out += ps
    if a.merge_review and Path(a.out).exists():
        from .perturb import merge_review
        out = merge_review(out, load_perturbations(a.out))
    write_jsonl(a.out, out)
    by_kind = {}
    for p in out:
        by_kind[p.kind] = by_kind.get(p.kind, 0) + 1
    print(f"wrote {len(out)} perturbation(s) -> {a.out} {by_kind}", file=sys.stderr)
    for line in LP.generation_log():
        print(line, file=sys.stderr)
    _ = PL
    return 0


def cmd_ledger_validate(a) -> int:
    from . import ledger_io, ledger_perturb as LP
    from .schema import load_perturbations
    cases = {c.case_id: c for c in ledger_io.load_cases(a.cases)}
    perts = load_perturbations(a.perturbations)
    lx = _base_lexicon(a)
    n_prob = 0
    for p in perts:
        c = cases.get(p.case_id)
        if c is None:
            print(f"{p.perturbation_id}: P5_CASE_MISSING")
            n_prob += 1
            continue
        probs = LP.verify(c, LP.apply(c, p, a.evidence_policy, lx), p, lx)
        for pr in probs:
            print(f"{p.perturbation_id}: {pr}")
        n_prob += len(probs)
    print(f"{len(perts)} perturbation(s), {n_prob} problem(s)", file=sys.stderr)
    return 1 if n_prob else 0


def cmd_ledger_export(a) -> int:
    from . import ledger_io, ledger_perturb as LP
    from .schema import load_perturbations
    cases = ledger_io.load_cases(a.cases)
    perts = load_perturbations(a.perturbations) if a.perturbations else []
    index = LP.export_variants(cases, perts, a.out, tuple(a.format.split(",")), not a.no_evidence, _base_lexicon(a))
    print(f"exported {len(index)} variant(s) -> {a.out}", file=sys.stderr)
    return 0


def cmd_ledger_run(a) -> int:
    from . import experiment, ledger_io, ledger_pipeline as PL
    from .schema import RUN_ID_RE, load_perturbations
    cases = ledger_io.load_cases(a.cases)
    perts = load_perturbations(a.perturbations) if a.perturbations else []
    efforts = a.efforts.split(",")
    client = _ledger_client(a)
    try:
        prompt = experiment.load_prompt(a.prompt)
    except OSError:
        return _err(f"prompt {a.prompt!r} not found", 2)
    run_dir = Path(a.out)
    lx = _base_lexicon(a)
    jobs = PL.plan(cases, perts, efforts, a.runs, a.seed, a.cases_filter.split(",") if a.cases_filter else None,
                   a.variants.split(",") if a.variants else None, a.allow_unreviewed, a.right_cue_fraction, not a.no_evidence, lx, a.evidence_policy)
    if not jobs:
        return _err("no jobs planned (are the perturbations approved? use --allow-unreviewed or `ledger perturb --approve-all`)")
    if (run_dir / "manifest.json").exists() and not a.force:
        manifest = experiment.read_manifest(run_dir)
        manifest["status"] = "running"
    else:
        try:
            desc = client.describe()
        except Exception as e:  # noqa: BLE001
            return _err(f"client unreachable: {e}", 4)
        if desc.get("describe_error") and a.client != "sim":
            print(f"warning: describe() incomplete: {desc['describe_error']}", file=sys.stderr)
        sampling = {"temperature": a.temperature, "top_p": 1.0, "max_tokens": a.max_tokens, "timeout_s": a.timeout}
        run_id = run_dir.name if RUN_ID_RE.match(run_dir.name) else experiment.new_run_id(random.Random(a.seed))
        manifest = PL.manifest_for(run_id, client, prompt, efforts, a.runs, a.seed, a.cases, a.perturbations, len(cases), len(perts),
                                   {"cases": a.cases_filter, "variants": a.variants, "allow_unreviewed": a.allow_unreviewed}, sampling, a.workers,
                                   a.notes or "", not a.no_evidence, lx)
    print(f"planned {len(jobs)} jobs -> {run_dir}", file=sys.stderr)
    try:
        counts = PL.run(jobs, client, run_dir, manifest, prompt, a.seed, workers=a.workers, redo_errors=a.redo_errors, force=a.force,
                        min_interval_ms=a.min_interval_ms, progress=_progress if not a.quiet else None,
                        sampling={"temperature": a.temperature, "max_tokens": a.max_tokens, "timeout_s": a.timeout})
        if a.with_ablation:
            counts["ablation"] = PL.ablate(run_dir, cases, perts, client, prompt, a.seed, a.ablation_runs, a.ablation_mode, None, lx,
                                           progress=_progress if not a.quiet else None, workers=a.workers)
    except experiment.ModelChanged as e:
        return _err(str(e), 3)
    print(json.dumps(counts))
    return 0


def cmd_ledger_ablate(a) -> int:
    from . import experiment, ledger_pipeline as PL
    cases, perts = PL.resolve_inputs(a.run_dir, a.cases, a.perturbations)
    client = _ledger_client(a) if a.client else None
    prompt = experiment.load_prompt(a.prompt)
    res = PL.ablate(a.run_dir, cases, perts, client, prompt, a.seed, a.runs, a.mode, a.export, _base_lexicon(a),
                    progress=_progress if not a.quiet else None)
    print(json.dumps(res))
    return 0


def cmd_ledger_import(a) -> int:
    from . import ledger_io, ledger_pipeline as PL
    from .schema import load_perturbations
    cases = ledger_io.load_cases(a.cases)
    perts = load_perturbations(a.perturbations) if a.perturbations else []
    paths = ledger_artefact_paths(a.paths)
    if not paths:
        return _err("no artefacts found", 2)
    res = PL.import_artefacts(paths, a.run_dir, cases, perts, a.index, a.effort, a.model, _base_lexicon(a))
    print(json.dumps(res, indent=1))
    return 1 if res["problems"] and a.strict else 0


def cmd_ledger_score(a) -> int:
    from . import ledger_pipeline as PL
    cases, perts = PL.resolve_inputs(a.run_dir, a.cases, a.perturbations)
    out = PL.score_all(a.run_dir, cases, perts, a.rule, a.B, a.seed, _base_lexicon(a), tuple(a.surfaces.split(",")), a.evidence_policy, progress=_progress)
    print(json.dumps({"probes": out["probes"], "run_id": out["summary"].get("run_id")}, indent=1))
    return 0


def cmd_ledger_validate_probes(a) -> int:
    from .validation import run_ledger_grid
    res = run_ledger_grid(a.grid, Path(a.out), a.seed, progress=_progress)
    print(res["markdown"])
    return 0 if res["passed"] else 1


def cmd_ledger_sample(a) -> int:
    from . import ledger as ledger_mod
    from .importers import load as load_artefact
    from .tools import ledger_labels as ll
    paths = ll.artefact_paths(a.source)
    if not paths:
        return _err(f"no artefacts under {a.source}", 2)
    items: list[dict] = []
    for path in paths:
        case, trace = load_artefact(path)
        items += ll.items_from_audit(ledger_mod.audit(case, trace))
    raters = [r.strip() for r in a.raters.split(",") if r.strip()]
    if not raters:
        return _err("--raters must name at least one rater")
    sampled = ll.sample(items, a.n, a.seed, a.per_case)
    written = ll.write_label_set(a.out, sampled, raters, a.seed, {"sources": [str(x) for x in paths], "n_items_available": len(items),
                                                                  "strata_available": ll.strata_counts(items)})
    print(f"{len(items)} gradable items in {len(paths)} artefact(s); sampled {len(sampled)} -> {written['grader']} (grades) and "
          f"{', '.join(str(written[r]) for r in raters)} (blind)")
    for k, v in ll.strata_counts(sampled).items():
        print(f"  {k}: {v}")
    return 0


def cmd_ledger_agreement(a) -> int:
    from .tools import ledger_labels as ll
    grader, raters, adj = ll.read_label_set(a.labels, a.adjudicated)
    if not raters:
        return _err(f"no rater files in {a.labels}")
    rep = ll.agreement(raters, grader, adj, B=a.B, seed=a.seed)
    print(json.dumps(rep, indent=1, ensure_ascii=False))
    print(ll.summary_text(rep), file=sys.stderr)
    return 0


def cmd_manifest(a) -> int:
    from .experiment import manifest_check, read_manifest
    if a.action == "show":
        print(json.dumps(read_manifest(a.run_dir), indent=1))
        return 0
    probs = manifest_check(a.run_dir, lex_mod.load(a.lexicon))
    for p in probs:
        print(p)
    print("manifest ok" if not probs else f"{len(probs)} problem(s)")
    return 1 if probs else 0


def cmd_recall(a) -> int:
    from .tools.extractor_recall import measure
    print(json.dumps(measure(a.labelled, a.run_dir), indent=1))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="traceaudit", description="Faithfulness and grounding audit for clinical LLM reasoning traces")
    p.add_argument("--version", action="version", version=f"traceaudit {__version__}")
    p.add_argument("--lexicon", default=None, help="override lexicon.json path")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("validate", help="check cases (and perturbations) against invariants C1, C2, P1")
    s.add_argument("cases"); s.add_argument("--perturbations"); s.set_defaults(fn=cmd_validate)

    s = sub.add_parser("casegen", help="generate synthetic cases")
    s.add_argument("-o", "--out", required=True); s.add_argument("--per-entity", type=int, default=20); s.add_argument("--seed", type=int, default=20261020)
    s.add_argument("--priors"); s.add_argument("--entities"); s.add_argument("--approve-all", action="store_true"); s.set_defaults(fn=cmd_casegen)

    s = sub.add_parser("review-sheet", help="export or import the haematologist review sheet")
    s.add_argument("cases"); s.add_argument("-o", "--out", default="review.csv"); s.add_argument("--import-csv"); s.add_argument("--reviewer", default="R01")
    s.add_argument("--date", default="1970-01-01"); s.set_defaults(fn=cmd_review_sheet)

    s = sub.add_parser("perturb", help="generate perturbation proposals")
    s.add_argument("cases"); s.add_argument("-o", "--out", required=True); s.add_argument("--seed", type=int, default=20261020)
    s.add_argument("--merge-review", action="store_true"); s.add_argument("--approve-all", action="store_true"); s.set_defaults(fn=cmd_perturb)

    s = sub.add_parser("run", help="run the model over cases x variants x efforts x runs")
    s.add_argument("--client", choices=["ollama", "openai", "anthropic", "sim"], required=True); s.add_argument("--model", required=True); s.add_argument("--endpoint")
    s.add_argument("--cases", required=True); s.add_argument("--perturbations"); s.add_argument("--out", required=True)
    s.add_argument("--efforts", default="low,medium,high"); s.add_argument("--runs", type=int, default=5); s.add_argument("--seed", type=int, default=20261020)
    s.add_argument("--cases-filter"); s.add_argument("--entities"); s.add_argument("--variants"); s.add_argument("--prompt", default="enable-v3")
    s.add_argument("--workers", type=int, default=1); s.add_argument("--allow-unreviewed", action="store_true"); s.add_argument("--allow-dirty")
    s.add_argument("--redo-errors", action="store_true"); s.add_argument("--force", action="store_true"); s.add_argument("--min-interval-ms", type=int, default=0)
    s.add_argument("--temperature", type=float, default=1.0); s.add_argument("--max-tokens", type=int, default=8192); s.add_argument("--timeout", type=float, default=600.0)
    s.add_argument("--notes"); s.add_argument("--quiet", action="store_true"); s.add_argument("--sim-p", type=float); s.add_argument("--sim-params")
    s.set_defaults(fn=cmd_run)

    for name, fn, hlp in (("ground", cmd_ground, "segment and ground traces"), ("score", cmd_score, "full scoring pipeline")):
        s = sub.add_parser(name, help=hlp)
        s.add_argument("run_dir"); s.add_argument("--cases"); s.add_argument("--perturbations"); s.add_argument("--verify", default="lexical", choices=["lexical", "retrieval", "none"])
        if name == "score":
            s.add_argument("--rule", default="D1", choices=["D1", "D2", "D3"]); s.add_argument("--B", type=int, default=2000); s.add_argument("--seed", type=int, default=20261020)
            s.add_argument("--judge", action="store_true"); s.add_argument("--judge-client", default="sim"); s.add_argument("--judge-model", default="simulated-judge")
            s.add_argument("--judge-endpoint"); s.add_argument("--judge-keys", help="file with trace_keys to judge")
        s.set_defaults(fn=fn)

    s = sub.add_parser("report", help="render summary.json"); s.add_argument("run_dir"); s.add_argument("--format", default="md", choices=["md", "json"]); s.set_defaults(fn=cmd_report)

    s = sub.add_parser("export", help="write the viewer bundle")
    s.add_argument("run_dir"); s.add_argument("-o", "--out", required=True); s.add_argument("--cases"); s.add_argument("--perturbations")
    s.add_argument("--single", action="store_true"); s.add_argument("--include-raw", action="store_true"); s.add_argument("--study-id")
    s.add_argument("--rating-n", type=int, default=100); s.add_argument("--seed", type=int, default=7731); s.add_argument("--ratings"); s.add_argument("--with-viewer")
    s.add_argument("--redact-prompt", action="store_true"); s.set_defaults(fn=cmd_export)

    s = sub.add_parser("import-ratings", help="validate and store viewer ratings"); s.add_argument("file"); s.add_argument("dest"); s.add_argument("--allow-unblinded", action="store_true"); s.set_defaults(fn=cmd_import_ratings)
    s = sub.add_parser("agreement", help="inter-rater and judge agreement"); s.add_argument("ratings"); s.add_argument("--judge"); s.add_argument("--B", type=int, default=2000); s.set_defaults(fn=cmd_agreement)

    s = sub.add_parser("demo", help="SimulatedModel end-to-end on the packaged sample")
    s.add_argument("--out", default="runs/demo"); s.add_argument("--runs", type=int, default=3); s.add_argument("--seed", type=int, default=20261020)
    s.add_argument("--sim-p", type=float, default=0.2); s.add_argument("--B", type=int, default=300); s.add_argument("--judge", action="store_true"); s.add_argument("--with-viewer")
    s.set_defaults(fn=cmd_demo)

    s = sub.add_parser("validate-probes", help="probe recovery on the simulator grid")
    s.add_argument("--grid", default="quick", choices=["quick", "default"]); s.add_argument("--out", default="runs/validate-probes"); s.add_argument("--seed", type=int, default=20261020)
    s.add_argument("--cases"); s.add_argument("--perturbations"); s.set_defaults(fn=cmd_validate_probes)

    s = sub.add_parser("serve", help="run the HTTP service (analyse traces, audit models) and the viewer")
    s.add_argument("--root", default="serve-data"); s.add_argument("--host", default="127.0.0.1"); s.add_argument("--port", type=int, default=8080)
    s.add_argument("--static", default=None, help="built viewer directory to serve at /")
    s.add_argument("--tokens", default=None, help="token:workspace,token:workspace (or TRACEAUDIT_TOKENS)")
    s.add_argument("--anonymous", default=None, choices=["none", "analyse", "all"], help="what unauthenticated requests may do (default analyse)")
    s.add_argument("--allow-clients", default=None, help="comma list of client kinds jobs may use (default sim)")
    s.add_argument("--rate", type=int, default=60, help="anonymous analyse requests per minute per address")
    s.add_argument("--cases", default=None, help="extra approved case set to offer: path to cases.jsonl (perturbations.jsonl beside it)")
    s.add_argument("--operator-key", action="append", default=[], metavar="KIND=ENV",
                   help="let jobs of this client kind run on a key held by the site, read from the named environment variable, e.g. anthropic=ANTHROPIC_API_KEY")
    s.add_argument("--max-calls-per-job", type=int, default=None); s.add_argument("--max-calls-per-day", type=int, default=None)
    s.add_argument("--domain", default=None, help="offer a packaged domain by default (e.g. haematology); default none built in")
    s.add_argument("--default-lexicon", default=None, help="offer this lexicon file as the default domain")
    s.add_argument("--examples", default=None, help="directory of starter lexicons (lexicon-<name>.json); default: examples/")
    s.set_defaults(fn=cmd_serve)
    s = sub.add_parser("cases", help="build cases from documents with known answers (any domain)")
    s.add_argument("action", choices=["build"]); s.add_argument("documents", help="JSONL of {case_id, entity, documents{section: text}, truth?}")
    s.add_argument("-o", "--out", required=True); s.add_argument("--approve", action="store_true", help="mark the built cases approved for runs")
    s.add_argument("--strict", action="store_true", help="drop cases with problems and exit 1 if any"); s.set_defaults(fn=cmd_cases)
    s = sub.add_parser("ledger", help="structured trace artefacts (facts + citations): audit, and later sample/agreement")
    ls = s.add_subparsers(dest="ledger_action", required=True)
    la = ls.add_parser("audit", help="audit one artefact, or many (directories and globs) with a summary and a review sheet")
    la.add_argument("paths", nargs="+", help="markdown artefact files, directories (all *.md inside) or globs")
    la.add_argument("--json", action="store_true"); la.add_argument("--summary", action="store_true", help="aggregate even for a single artefact")
    la.add_argument("--review-sheet", metavar="CSV", help="write every citation grade and uncited assertion as a row for human review")
    la.set_defaults(fn=cmd_ledger_audit)
    lc = ls.add_parser("cases", help="base ledger cases from artefacts (one per case id; repeats must agree)")
    lc.add_argument("paths", nargs="+"); lc.add_argument("-o", "--out", required=True); lc.add_argument("--strict", action="store_true"); lc.set_defaults(fn=cmd_ledger_cases)
    lp = ls.add_parser("perturb", help="generate decisive, neutral, anchor-loss and authority perturbations for ledger cases")
    lp.add_argument("cases"); lp.add_argument("-o", "--out", required=True); lp.add_argument("--kinds", default="decisive,neutral,anchor_loss,authority")
    lp.add_argument("--expectations", default="structured,reference,lexicon", help="expectation sources: structured,reference,lexicon[,rationale]")
    lp.add_argument("--rationale-from", help="run directory or artefacts whose base rationales supply (model-derived, flagged) expectations")
    lp.add_argument("--max-decisive", type=int, default=2); lp.add_argument("--max-flips", type=int, default=3); lp.add_argument("--anchor-op", default="untest", choices=["untest", "flip"])
    lp.add_argument("--include-right", action="store_true", help="always include the right-cue control (default: seeded coin per case)")
    lp.add_argument("--seed", type=int, default=20261020); lp.add_argument("--approve-all", action="store_true"); lp.add_argument("--merge-review", action="store_true")
    lp.set_defaults(fn=cmd_ledger_perturb)
    lv = ls.add_parser("validate", help="ledger invariant P1 over cases and perturbations")
    lv.add_argument("cases"); lv.add_argument("--perturbations", required=True); lv.add_argument("--evidence-policy", default="rewrite", choices=["rewrite", "synthesize", "redact"])
    lv.set_defaults(fn=cmd_ledger_validate)
    le = ls.add_parser("export", help="write base cases and variants (json, md) for an external engine")
    le.add_argument("cases"); le.add_argument("--perturbations"); le.add_argument("-o", "--out", required=True); le.add_argument("--format", default="json,md")
    le.add_argument("--no-evidence", action="store_true"); le.set_defaults(fn=cmd_ledger_export)
    lr = ls.add_parser("run", help="prompt a model with rendered ledger cases x variants x efforts x runs")
    lr.add_argument("--client", choices=["ollama", "openai", "anthropic", "sim"], required=True); lr.add_argument("--model", default="simulated-ledger"); lr.add_argument("--endpoint")
    lr.add_argument("--cases", required=True); lr.add_argument("--perturbations"); lr.add_argument("--out", required=True)
    lr.add_argument("--efforts", default="low,medium,high"); lr.add_argument("--runs", type=int, default=3); lr.add_argument("--seed", type=int, default=20261020)
    lr.add_argument("--cases-filter"); lr.add_argument("--variants"); lr.add_argument("--prompt", default="ledger-v1"); lr.add_argument("--right-cue-fraction", type=float, default=0.5)
    lr.add_argument("--no-evidence", action="store_true"); lr.add_argument("--evidence-policy", default="rewrite", choices=["rewrite", "synthesize", "redact"])
    lr.add_argument("--workers", type=int, default=1); lr.add_argument("--allow-unreviewed", action="store_true")
    lr.add_argument("--redo-errors", action="store_true"); lr.add_argument("--force", action="store_true"); lr.add_argument("--min-interval-ms", type=int, default=0)
    lr.add_argument("--temperature", type=float, default=1.0); lr.add_argument("--max-tokens", type=int, default=8192); lr.add_argument("--timeout", type=float, default=600.0)
    lr.add_argument("--notes"); lr.add_argument("--quiet", action="store_true"); lr.add_argument("--sim-p", type=float); lr.add_argument("--sim-params")
    lr.add_argument("--with-ablation", action="store_true"); lr.add_argument("--ablation-runs", type=int, default=1); lr.add_argument("--ablation-mode", default="remove", choices=["remove", "mask"])
    lr.set_defaults(fn=cmd_ledger_run)
    lab = ls.add_parser("ablate", help="second pass: remove each base trace's stated discriminators and rerun (or export for an engine)")
    lab.add_argument("run_dir"); lab.add_argument("--cases"); lab.add_argument("--perturbations"); lab.add_argument("--client", choices=["ollama", "openai", "anthropic", "sim"])
    lab.add_argument("--model", default="simulated-ledger"); lab.add_argument("--endpoint"); lab.add_argument("--prompt", default="ledger-v1")
    lab.add_argument("--runs", type=int, default=1); lab.add_argument("--mode", default="remove", choices=["remove", "mask"]); lab.add_argument("--export")
    lab.add_argument("--seed", type=int, default=20261020); lab.add_argument("--quiet", action="store_true"); lab.add_argument("--sim-p", type=float); lab.add_argument("--sim-params")
    lab.set_defaults(fn=cmd_ledger_ablate)
    li = ls.add_parser("import", help="artefacts an external engine produced for exported variants become traces")
    li.add_argument("paths", nargs="+"); li.add_argument("--run-dir", required=True); li.add_argument("--cases", required=True); li.add_argument("--perturbations")
    li.add_argument("--index", help="index.jsonl written by `ledger export`"); li.add_argument("--effort"); li.add_argument("--model", default="external")
    li.add_argument("--strict", action="store_true"); li.set_defaults(fn=cmd_ledger_import)
    lsc = ls.add_parser("score", help="parse, audit and score a ledger run; writes summary.json and long.csv")
    lsc.add_argument("run_dir"); lsc.add_argument("--cases"); lsc.add_argument("--perturbations"); lsc.add_argument("--rule", default="D1", choices=["D1", "D2", "D3", "D1R"])
    lsc.add_argument("--surfaces", default="thinking,report"); lsc.add_argument("--evidence-policy", default="rewrite", choices=["rewrite", "synthesize", "redact"])
    lsc.add_argument("--B", type=int, default=2000); lsc.add_argument("--seed", type=int, default=20261020); lsc.set_defaults(fn=cmd_ledger_score)
    lvp = ls.add_parser("validate-probes", help="ledger probe recovery on the synthetic simulator grid")
    lvp.add_argument("--grid", default="quick", choices=["quick", "default"]); lvp.add_argument("--out", default="runs/validate-ledger-probes")
    lvp.add_argument("--seed", type=int, default=20261020); lvp.set_defaults(fn=cmd_ledger_validate_probes)
    x = ls.add_parser("sample", help="write grader.jsonl and blind per-rater files for a sample of citations (spec 20)")
    x.add_argument("source", help="artefact file, or a directory searched for *.md"); x.add_argument("--n", type=int, default=300)
    x.add_argument("--raters", default="R01,R02", help="comma list of rater ids"); x.add_argument("--seed", type=int, default=20261029)
    x.add_argument("--per-case", type=int, default=None, help="cap per case (default: twice the even share, at least 5)")
    x.add_argument("-o", "--out", default="labels"); x.set_defaults(fn=cmd_ledger_sample)
    x = ls.add_parser("agreement", help="inter-rater and grader-vs-consensus agreement over a labels directory (spec 20)")
    x.add_argument("labels", help="directory with grader.jsonl and <rater>.jsonl"); x.add_argument("--adjudicated", default=None, help="jsonl of {item_id, human_grade}")
    x.add_argument("--B", type=int, default=2000); x.add_argument("--seed", type=int, default=20261029); x.set_defaults(fn=cmd_ledger_agreement)
    s = sub.add_parser("manifest", help="check or show a run manifest"); s.add_argument("action", choices=["check", "show"]); s.add_argument("run_dir"); s.set_defaults(fn=cmd_manifest)
    s = sub.add_parser("recall", help="extractor recall against clinician labels"); s.add_argument("labelled"); s.add_argument("run_dir"); s.set_defaults(fn=cmd_recall)
    return p


def main(argv: list[str] | None = None) -> int:
    p = build_parser()
    a = p.parse_args(argv)
    try:
        return a.fn(a)
    except FileNotFoundError as e:
        return _err(str(e), 2)


if __name__ == "__main__":
    sys.exit(main())
