// `POST /api/analyse`: the text path as an adapter onto the fact ledger (specs/18-fact-ledger.md §1). The response is
// a ledger result plus the documents with each fact's evidence span, so the page renders the ledger views and a
// documents pane whose highlights are the facts. No React here so the mapping is unit-testable against the fixture.
import { parseLedgerResult, type Fact, type LedgerResult, type LedgerSection } from './ledger';
import type { ReportHighlight } from '../components/ReportPane';
import type { HighlightKind } from './spans';

export interface AnalyseDocumentFact { id: string; start: number; end: number }
export interface AnalyseDocument { id: string; title: string; text: string; facts: AnalyseDocumentFact[] }
export interface AnalyseLexicon { id: string; domain: string; version: string; entities: Array<{ id: string; display: string }>; findings: Array<{ id: string; display: string; kind: string }> }
/** The parsed answer and the claim counts the adapter recorded. */
export interface AnalyseAnswer { text: string; entity: string | null; entity_raw: string | null; subtype: string | null; hedged: boolean; entities_named: string[]; claims: number; factual_claims: number }
/** The text path's headline numbers, which `parseLedgerResult` does not carry. */
export interface AnalyseHeadline { grounding_rate: number | null; uncited_assertions: number }

export interface AnalyseResponse extends LedgerResult {
  documents: AnalyseDocument[];
  /** The lexicon the analysis used, with display names for its categories and findings. */
  lexicon: AnalyseLexicon | null;
  answer: AnalyseAnswer | null;
  headline: AnalyseHeadline;
  /** `truth` when the caller supplied a truth table, else `extracted` (the documents' own assertions). */
  oracle: 'truth' | 'extracted';
  warnings: string[];
  domain: string | null;
}

/** Validate the ledger part with `parseLedgerResult`, then the documents the page highlights. */
export function parseAnalyseResponse(raw: unknown): AnalyseResponse {
  const base = parseLedgerResult(raw);
  const r = raw as Record<string, unknown>;
  const docsRaw = r.documents;
  if (!Array.isArray(docsRaw)) throw new Error('analyse result: documents is not an array');
  const documents: AnalyseDocument[] = docsRaw.map((d) => {
    const doc = (d ?? {}) as Partial<AnalyseDocument>;
    if (typeof doc.id !== 'string') throw new Error('analyse result: malformed document');
    const text = typeof doc.text === 'string' ? doc.text : '';
    const facts = (Array.isArray(doc.facts) ? doc.facts : [])
      .filter((f): f is AnalyseDocumentFact => !!f && typeof f.id === 'string' && typeof f.start === 'number' && typeof f.end === 'number');
    return { id: doc.id, title: typeof doc.title === 'string' && doc.title ? doc.title : doc.id, text, facts };
  });
  const lexicon = r.lexicon && typeof r.lexicon === 'object' ? r.lexicon as AnalyseLexicon : null;
  const a = r.answer && typeof r.answer === 'object' ? r.answer as Partial<AnalyseAnswer> : null;
  const answer: AnalyseAnswer | null = a ? {
    text: typeof a.text === 'string' ? a.text : '', entity: str(a.entity), entity_raw: str(a.entity_raw), subtype: str(a.subtype), hedged: !!a.hedged,
    entities_named: Array.isArray(a.entities_named) ? a.entities_named.filter((x): x is string => typeof x === 'string') : [],
    claims: num(a.claims), factual_claims: num(a.factual_claims),
  } : null;
  const metrics = (r.metrics ?? {}) as Record<string, unknown>;
  const rate = metrics.grounding_rate;
  return {
    ...base,
    documents,
    lexicon,
    answer,
    headline: { grounding_rate: typeof rate === 'number' && Number.isFinite(rate) ? rate : null, uncited_assertions: num(metrics.uncited_assertions) },
    oracle: r.oracle === 'truth' ? 'truth' : 'extracted',
    warnings: Array.isArray(r.warnings) ? r.warnings.filter((w): w is string => typeof w === 'string') : [],
    domain: str(r.domain) ?? lexicon?.domain ?? null,
  };
}
const str = (v: unknown) => (typeof v === 'string' ? v : null);
const num = (v: unknown) => (typeof v === 'number' && Number.isFinite(v) ? v : 0);

// ---- documents pane ------------------------------------------------------------------------------

export type FactStatus = 'agree' | 'disagree' | 'unverifiable' | 'referenced' | 'ignored' | 'context';
export const FACT_STATUS_TEXT: Record<FactStatus, string> = {
  agree: 'cited in the reasoning, stated as recorded',
  disagree: 'cited in the reasoning with the opposite value',
  unverifiable: 'cited in the reasoning, value not verifiable',
  referenced: 'named in the reasoning, not cited',
  ignored: 'never referenced',
  context: 'context given with the documents',
};
const STATUS_KIND: Record<FactStatus, HighlightKind> = { agree: 'supported', disagree: 'contradicted', unverifiable: 'unsupported', referenced: 'mention', ignored: 'other', context: 'cue' };

/** The worst grade a fact received across the report's citations, else how it was (not) referenced. */
export function factStatus(f: Fact, sections: LedgerSection[]): FactStatus {
  if (f.source === 'context') return 'context';
  let best: FactStatus | null = null;
  for (const s of sections) for (const seg of s.segments) for (const c of seg.cited) {
    if (c.id !== f.id) continue;
    if (c.grade === 'disagree') return 'disagree';
    if (c.grade === 'agree') best = best ?? 'agree';
    else if (c.grade === 'unverifiable' || c.grade === 'not_mentioned') best = 'unverifiable';
  }
  if (best) return best;
  return f.referenced_in_thinking ? 'referenced' : 'ignored';
}

export interface HighlightOptions {
  /** The fact under the pointer (drawn as focus). */
  highlight?: string | null;
  /** Display names for finding ids, when the lexicon carries them. */
  findingDisplay?: (field: string) => string;
}

/** One highlight per fact span, coloured by the fact's status; `id` is the fact id so a click can jump to its row. */
export function documentHighlights(res: Pick<AnalyseResponse, 'documents' | 'facts' | 'sections'>, opts: HighlightOptions = {}): ReportHighlight[] {
  const facts = new Map(res.facts.map((f) => [f.id, f] as const));
  const out: ReportHighlight[] = [];
  for (const d of res.documents) {
    for (const sp of d.facts) {
      const f = facts.get(sp.id);
      if (!f) continue;
      const status = factStatus(f, res.sections);
      const field = opts.findingDisplay ? opts.findingDisplay(f.field) : f.field;
      const focus = opts.highlight === f.id;
      out.push({ report: d.id, start: sp.start, end: sp.end, id: f.id, kind: focus ? 'focus' : STATUS_KIND[status], priority: focus ? 2 : 1, title: `${f.id} · ${field} = ${f.value} · ${FACT_STATUS_TEXT[status]}` });
    }
  }
  return out;
}

/** The file a user downloads: the request (no secrets are involved here) plus the service's response. */
export function analyseExport(request: unknown, response: AnalyseResponse, meta: { api_base: string; lexicon_version: string | null; lexicon_id?: string | null; domain?: string | null; analysed_at: string }) {
  return { schema: 'traceaudit-analyse-result/2', meta, request, response };
}
