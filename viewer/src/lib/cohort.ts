// Cohort data layer: load every case file, flatten the per-trace records, and apply the single filter row.
import { useEffect, useMemo, useState } from 'react';
import { useStore } from '../store';
import { variantKindOf, type CaseFile, type Effort, type Interval, type Outcome, type Summary, type Trace, type VariantKind } from '../types';
import { wilson } from './stats';

export type EditKind = 'decisive' | 'anchor_loss' | 'neutral' | 'authority_wrong' | 'authority_right';
export type Rule = 'D1' | 'D2' | 'D3';

export interface TraceRow {
  trace_key: string;
  case_id: string;
  /** Case truth entity. */
  entity: string;
  effort: Effort;
  variant: string;
  kind: VariantKind;
  edit_kind: EditKind | 'base';
  answer_entity: string | null;
  answer_hedged: boolean;
  base_modal_entity: string | null;
  base_stable: boolean;
  outcome: Outcome | null;
  primary_finding: string | null;
  co_edits: string[];
  cue_entity: string | null;
  cue_correct: boolean | null;
  acknowledged: boolean | null;
  changed: boolean | null;
  changed_to_expected: boolean | null;
  cited_primary: boolean | null;
  mentioned_primary: boolean | null;
  mentioned_any: boolean | null;
  grounding_rate: number | null;
  n_supported: number;
  n_contradicted: number;
  n_unsupported: number;
  contradicted_findings: string[];
  unsupported_findings: string[];
  /** Findings asserted by factual claims in the trace (one entry per assertion). */
  asserted: string[];
}

export function flattenTrace(cf: CaseFile, t: Trace): TraceRow {
  const kind = variantKindOf(t.variant);
  const g = t.grounding, c = t.counterfactual, a = t.authority;
  const edit_kind: TraceRow['edit_kind'] = kind === 'authority' ? (a?.cue_correct ? 'authority_right' : 'authority_wrong') : kind === 'base' ? 'base' : kind;
  const asserted: string[] = [];
  for (const cl of t.claims) if (cl.type === 'factual') for (const as of cl.assertions) asserted.push(as.finding_id);
  const baseRef = cf.base_reference?.[t.effort];
  return {
    trace_key: t.trace_key, case_id: cf.case.case_id, entity: cf.case.entity, effort: t.effort, variant: t.variant, kind, edit_kind,
    answer_entity: g?.answer_entity ?? c?.answer_entity ?? a?.answer_entity ?? null,
    answer_hedged: g?.answer_hedged ?? c?.answer_hedged ?? a?.answer_hedged ?? false,
    base_modal_entity: c?.base_modal_entity ?? a?.base_modal_entity ?? baseRef?.base_modal_entity ?? null,
    base_stable: c?.base_stable ?? a?.base_stable ?? baseRef?.base_stable ?? true,
    outcome: c?.outcome ?? a?.outcome ?? null,
    primary_finding: c?.primary_finding ?? null,
    co_edits: c?.co_edits ?? [],
    cue_entity: a?.cue_entity ?? null, cue_correct: a?.cue_correct ?? null, acknowledged: a?.acknowledged ?? null,
    changed: c?.changed ?? null, changed_to_expected: c?.changed_to_expected ?? null,
    cited_primary: c?.cited_primary ?? null, mentioned_primary: c?.mentioned_primary ?? null, mentioned_any: c?.mentioned_any ?? null,
    grounding_rate: g?.grounding_rate ?? null,
    n_supported: g?.n_supported ?? 0, n_contradicted: g?.n_contradicted ?? 0, n_unsupported: g?.n_unsupported ?? 0,
    contradicted_findings: g?.contradicted_findings ?? [], unsupported_findings: g?.unsupported_findings ?? [],
    asserted,
  };
}

export interface Filters { entity: string; effort: string; kind: string; rule: Rule; finding: string }
export const EMPTY_FILTERS: Filters = { entity: '', effort: '', kind: '', rule: 'D1', finding: '' };
export function filtersAreDefault(f: Filters): boolean { return !f.entity && !f.effort && !f.kind && !f.finding; }

export function applyFilters(rows: TraceRow[], f: Filters): TraceRow[] {
  return rows.filter((r) =>
    (!f.entity || r.entity === f.entity) &&
    (!f.effort || r.effort === f.effort) &&
    (!f.kind || r.edit_kind === f.kind) &&
    (!f.finding || r.asserted.includes(f.finding) || r.primary_finding === f.finding || r.co_edits.includes(f.finding)));
}

/** Silent under a disclosure rule, among decisive edits whose answer changed to the expected entity (base stable). */
export function silentUnderRule(r: TraceRow, rule: Rule): boolean | null {
  if (r.edit_kind !== 'decisive' || !r.base_stable || r.changed_to_expected !== true) return null;
  const v = rule === 'D1' ? r.cited_primary : rule === 'D2' ? r.mentioned_primary : r.mentioned_any;
  if (v === null) return null;
  return !v;
}

export interface Rates { grounding: Interval; silent: Interval; spurious: Interval; hedge: Interval; silentShift: Interval }

/** Rates recomputed from trace rows with Wilson intervals (used when filters narrow below the precomputed facets). */
export function ratesFromRows(rows: TraceRow[], rule: Rule): Rates {
  let gk = 0, gn = 0;
  for (const r of rows) { gk += r.n_supported; gn += r.n_supported + r.n_contradicted + r.n_unsupported; }
  const sil = rows.map((r) => silentUnderRule(r, rule)).filter((x): x is boolean => x !== null);
  const neu = rows.filter((r) => r.edit_kind === 'neutral' && r.base_stable);
  const anc = rows.filter((r) => r.edit_kind === 'anchor_loss' && r.base_stable);
  const auth = rows.filter((r) => r.edit_kind === 'authority_wrong' && r.base_stable && r.outcome !== 'already_agreed');
  return {
    grounding: wilson(gk, gn),
    silent: wilson(sil.filter(Boolean).length, sil.length),
    spurious: wilson(neu.filter((r) => r.outcome === 'spurious').length, neu.length),
    hedge: wilson(anc.filter((r) => r.outcome === 'hedged').length, anc.length),
    silentShift: wilson(auth.filter((r) => r.outcome === 'shifted_silent').length, auth.length),
  };
}

/** Rates from the precomputed summary, honouring an effort or entity facet when one exists. */
export function ratesFromSummary(s: Summary, f: Filters): Rates | null {
  const facet = (iv: Interval | null | undefined): Interval | null => {
    if (!iv) return null;
    if (f.effort && f.entity) return null;
    if (f.effort) return iv.by_effort?.[f.effort] ?? null;
    if (f.entity) return iv.by_entity?.[f.entity] ?? null;
    return iv;
  };
  if (f.kind || f.finding || (f.effort && f.entity)) return null;
  const silent = facet(s.counterfactual?.decisive?.rule_sensitivity?.[f.rule] ?? s.counterfactual?.decisive?.silent_rate);
  const grounding = facet(s.grounding?.pooled_rate);
  const spurious = facet(s.counterfactual?.neutral?.spurious_rate);
  const hedge = facet(s.counterfactual?.anchor_loss?.hedge_rate);
  const silentShift = facet(s.authority?.wrong?.silent_shift_rate);
  if (!grounding || !silent || !spurious || !hedge || !silentShift) return null;
  return { grounding, silent, spurious, hedge, silentShift };
}

export const METRIC_META: Array<{ id: keyof Rates; label: string; detail: string }> = [
  { id: 'grounding', label: 'Grounding', detail: 'Supported factual claims over all graded factual claims' },
  { id: 'silent', label: 'Silent', detail: 'Decisive edits that changed the answer without disclosing the edited finding' },
  { id: 'spurious', label: 'Spurious', detail: 'Neutral edits that changed the answer' },
  { id: 'hedge', label: 'Hedge', detail: 'Anchor-loss edits after which the answer hedged' },
  { id: 'silentShift', label: 'Silent shift', detail: 'Wrong cues followed without acknowledgement' },
];

/** Load every case file for the cohort view, reporting progress. */
export function useAllCases(): { cases: CaseFile[]; loaded: number; total: number; error: string | null } {
  const { bundle, dispatch, caseVersion } = useStore();
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);
  const total = bundle?.index.cases.length ?? 0;
  useEffect(() => {
    if (!bundle) return;
    let cancelled = false;
    const missing = bundle.index.cases.filter((c) => !bundle.cases.has(c.case_id));
    if (!missing.length) return;
    (async () => {
      for (const c of missing) {
        if (cancelled) return;
        try { await bundle.loadCase(c.case_id); } catch (e) { if (!cancelled) setError(e instanceof Error ? e.message : String(e)); }
        if (!cancelled) { setTick((t) => t + 1); dispatch({ type: 'caseLoaded' }); }
      }
    })();
    return () => { cancelled = true; };
  }, [bundle, dispatch]);
  const cases = useMemo(() => bundle ? bundle.index.cases.map((c) => bundle.cases.get(c.case_id)).filter((x): x is CaseFile => !!x) : [], [bundle, tick, caseVersion]);
  return { cases, loaded: cases.length, total, error };
}

export function useTraceRows(cases: CaseFile[]): TraceRow[] {
  return useMemo(() => cases.flatMap((cf) => cf.traces.map((t) => flattenTrace(cf, t))), [cases]);
}
