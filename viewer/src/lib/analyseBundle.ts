// Turn one `/api/analyse` response into the in-memory objects the existing grounding components take:
// a CaseFile with a single `base` variant and one Trace, wrapped in a Bundle so the full trace views can open it.
import type { AnalyseRequest, AnalyseResponse, LexiconDisplay } from './api';
import type { Bundle, BundleIndex, CaseFile, Effort, Interval, Lexicon, Reports, Section, Trace } from '../types';
import { sectionsFor } from './documents';

export interface SingleTraceBundle { bundle: Bundle; caseFile: CaseFile; trace: Trace; traceKey: string }

export interface BuildOptions {
  effort?: Effort;
  runId?: string;
  /** Overrides the lexicon's version for the provenance strip. */
  now?: Date;
}

/** The documents the case has, in section order: the response's, else the request's (`documents` or `reports`). */
function caseDocuments(req: AnalyseRequest, res: AnalyseResponse): { reports: Reports; sections: Section[] } {
  const source: Partial<Reports> = res.case?.reports ?? req.documents ?? req.reports ?? {};
  const declared = res.case?.sections ?? (req.titles ? Object.keys(req.documents ?? {}).map((id) => ({ id, title: req.titles?.[id] ?? id })) : null);
  const sections = sectionsFor(source, declared);
  const reports: Reports = {};
  for (const s of sections) reports[s.id] = source[s.id] ?? '';
  return { reports, sections };
}

function interval(point: number | null, n?: number): Interval {
  return { point, lo: null, hi: null, n_records: n };
}

/** The lexicon to render with: the response's own (display names for its categories and findings) when present,
 *  else the one the caller fetched. */
function lexiconFor(res: AnalyseResponse, fallback: LexiconDisplay | Lexicon): Lexicon {
  if (res.lexicon) {
    return {
      version: res.lexicon.version,
      entities: res.lexicon.entities.map((e) => ({ id: e.id, display: e.display, in_scope: fallback.entities.find((x) => x.id === e.id)?.in_scope ?? true })),
      findings: res.lexicon.findings,
      discriminators: (fallback as Lexicon).discriminators,
      linked: (fallback as Lexicon).linked,
    };
  }
  return { version: fallback.version, entities: fallback.entities, findings: fallback.findings, discriminators: (fallback as Lexicon).discriminators, linked: (fallback as Lexicon).linked };
}

export function buildSingleTraceBundle(req: AnalyseRequest, res: AnalyseResponse, lexicon: LexiconDisplay | Lexicon, opts: BuildOptions = {}): SingleTraceBundle {
  const effort: Effort = opts.effort ?? 'medium';
  const caseId = res.case?.case_id || 'analysed';
  const traceKey = `${caseId}|base|${effort}|0`;
  const { reports, sections } = caseDocuments(req, res);
  const truth = res.case?.truth ?? req.truth ?? {};
  const findingSpans = res.case?.finding_spans ?? {};
  const entity = res.case?.entity ?? req.entity ?? res.grounding?.answer_entity ?? 'unknown';

  const claims = (res.claims ?? []).map((c) => ({ ...c, trace_key: traceKey }));
  const grounding = res.grounding ? { ...res.grounding, trace_key: traceKey, case_id: caseId, variant: 'base', effort, run: 0 } : null;
  const trace: Trace = {
    trace_key: traceKey,
    variant: 'base',
    effort,
    run: 0,
    reasoning: req.reasoning,
    answer: req.answer,
    retrieved: [],
    meta: { latency_ms: null, usage: {}, finish_reason: null, error: null },
    claims,
    grounding,
    counterfactual: null,
    authority: null,
    judge: null,
    map: res.map ?? null,
  };
  const missing = sections.filter((s) => !reports[s.id]).map((s) => s.id);
  const caseFile: CaseFile = {
    case: { case_id: caseId, entity, subtype: null, flags: { discordant: false, incomplete: false, atypical_features: [], missing_modalities: missing }, reports, truth, finding_spans: findingSpans, sections },
    variants: { base: { variant: 'base', kind: 'base', reports, truth_after: truth, perturbation: null, diff: {}, finding_spans: findingSpans } },
    traces: [trace],
    base_reference: {
      low: { base_modal_entity: null, base_mode_share: null, base_stable: false, base_n: 0 },
      medium: { base_modal_entity: null, base_mode_share: null, base_stable: false, base_n: 0 },
      high: { base_modal_entity: null, base_mode_share: null, base_stable: false, base_n: 0 },
    },
  };
  caseFile.base_reference[effort] = { base_modal_entity: grounding?.answer_entity ?? null, base_mode_share: grounding ? 1 : null, base_stable: !!grounding, base_n: 1 };

  const now = opts.now ?? new Date();
  const runId = opts.runId ?? `analyse-${now.toISOString().replace(/[-:]/g, '').replace(/\.\d+Z$/, 'Z')}`;
  const lex = lexiconFor(res, lexicon);
  const nFactual = grounding?.n_factual ?? claims.filter((c) => c.type === 'factual').length;
  const domain = res.domain ?? res.lexicon?.domain ?? (lexicon as LexiconDisplay).domain;
  const index: BundleIndex = {
    bundle_version: 1,
    run: { run_id: runId, manifest: { model: { tag: 'analysed trace' }, effort_mechanism: 'not applicable', notes: `Single trace analysed via /api/analyse; oracle: ${res.oracle}${domain ? `; domain: ${domain}` : ''}` } },
    lexicon: lex,
    rubric: { dimensions: [], error_tags: [] },
    cases: [{ case_id: caseId, entity, subtype: null, flags: caseFile.case.flags, variants: ['base'], n_traces: 1, file: `cases/${caseId}.json` }],
    summary: {
      run_id: runId,
      generated: now.toISOString(),
      scoring: { rule: 'D1', verifier: 'lexical', B: 0, seed: 0 },
      counts: { traces: 1, errors: 0, cases: 1, by_variant_kind: { base: 1 }, by_effort: { [effort]: 1 }, unstable_base_pairs: 0, base_pairs: 0 },
      grounding: {
        pooled_rate: interval(grounding?.grounding_rate ?? null, nFactual),
        mean_trace_rate: interval(grounding?.grounding_rate ?? null, 1),
        traces_with_contradiction: interval(grounding ? (grounding.n_contradicted > 0 ? 1 : 0) : null, 1),
        traces_with_unsupported: interval(grounding ? (grounding.n_unsupported > 0 ? 1 : 0) : null, 1),
        label_counts: grounding ? { supported: grounding.n_supported, contradicted: grounding.n_contradicted, unsupported: grounding.n_unsupported, ambiguous: grounding.n_ambiguous } : undefined,
        claim_type_counts: grounding ? { factual: grounding.n_factual, inferential: grounding.n_inferential, knowledge: grounding.n_knowledge, other: grounding.n_other } : undefined,
      },
    },
    study: null,
    ratings: null,
  };
  const cases = new Map<string, CaseFile>([[caseId, caseFile]]);
  const bundle: Bundle = {
    index,
    cases,
    loadCase: (id) => (id === caseId ? Promise.resolve(caseFile) : Promise.reject(new Error(`Unknown case ${id}`))),
    source: 'analyse',
  };
  return { bundle, caseFile, trace, traceKey };
}

/** The file a user downloads: request (no secrets are involved here) plus the service's response. */
export function analyseExport(req: AnalyseRequest, res: AnalyseResponse, meta: { api_base: string; lexicon_version: string | null; lexicon_id?: string | null; domain?: string | null; analysed_at: string }) {
  return { schema: 'traceaudit-analyse-result/1', meta, request: req, response: res };
}
