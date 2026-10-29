// The fact ledger: types for `POST /api/ledger` and the pure helpers the Fact ledger result page is built from.
// No React here so every mapping can be unit-tested against the service fixture.

export type CheckStatus = 'PASS' | 'FAIL';
export interface LedgerCheck { id: string; title: string; status: CheckStatus; detail: string }

export interface LedgerMetrics {
  facts: number;
  patient_facts: number;
  context_facts: number;
  reference_facts: number;
  cited_in_report: number;
  cited_agree: number;
  cited_disagree: number;
  cited_unverifiable: number;
  thinking_chars: number;
  thinking_ids: number;
  thinking_fields?: number;
  candidates_named_in_thinking: Record<string, number>;
  ignored: number;
  ignored_informative: number;
  checks_failed: number;
  checks_total: number;
}

export type CitationGrade = 'agree' | 'disagree' | 'unverifiable' | 'not_mentioned' | 'not_found' | 'reference';
export interface Citation {
  id: string;
  grade: CitationGrade;
  field?: string | null;
  value?: string | null;
  /** What the report actually said about the fact, when the grader could extract it. */
  stated?: string | null;
  candidate?: string | null;
}
/** An assertion the grader found in the segment's text that cites no fact: `fact_id` is the fact it matched, if any. */
export interface UncitedAssertion { field: string; stated?: string | null; fact_id?: string | null; value?: string | null; grade: string }
export interface LedgerSegment { text: string; citation_ids: string[]; cited: Citation[]; uncited_assertions: UncitedAssertion[]; informative: boolean }
export interface LedgerSection { title: string; segments: LedgerSegment[] }

/** `patient` and `context` are the case; everything else (`who`, …) is reference material. */
export type FactSource = 'patient' | 'context' | string;
export interface Fact {
  id: string;
  source: FactSource;
  section: string;
  field: string;
  value: string;
  evidence: string;
  candidate: string | null;
  polarity: 'pos' | 'neg' | 'untested' | 'other' | string;
  informative: boolean;
  referenced_in_thinking: boolean;
  cited_in_report: boolean;
  cited_in_rationale: boolean;
  ignored: boolean;
}

export interface LedgerThinking { text: string; ids: string[]; candidates: string[] }

export type CriterionStatus = 'met' | 'not_met' | 'not_assessable' | string;
export interface Criterion { criterion: string; status: CriterionStatus; ids: string[] }
export interface DifferentialRow { diagnosis: string; verdict: string; supporting: string[]; contradicting: string[]; rationale: string; criteria: Criterion[] }
export interface KeyFinding { modality?: string; description: string; ids: string[] }
export interface Discriminator { text: string; ids: string[] }
export interface LedgerRationale {
  decision: string | null;
  confidence?: string | null;
  key_findings: KeyFinding[];
  differential: DifferentialRow[];
  discriminators: Discriminator[];
  unresolved: string[];
  would_change: string[];
}

export interface LedgerAblation { removed_ids: string[]; decision_before: string | null; decision_after: string | null; changed: boolean }

export interface LedgerResult {
  case_id?: string | null;
  truth: string | null;
  decision: string | null;
  candidates: string[];
  checks: LedgerCheck[];
  metrics: LedgerMetrics;
  sections: LedgerSection[];
  facts: Fact[];
  thinking: LedgerThinking | null;
  rationale: LedgerRationale | null;
  ablation: LedgerAblation | null;
}

export type LedgerRequest = { markdown: string } | { case: Record<string, unknown>; trace: Record<string, unknown> };

// ---- parsing -------------------------------------------------------------------------------------

/** Validate the shape the page relies on; throws a readable error when a field the page needs is missing. */
export function parseLedgerResult(raw: unknown): LedgerResult {
  if (!raw || typeof raw !== 'object') throw new Error('ledger result is not an object');
  const r = raw as Record<string, unknown>;
  const arr = <T,>(k: string): T[] => {
    const v = r[k];
    if (v === undefined || v === null) return [];
    if (!Array.isArray(v)) throw new Error(`ledger result: ${k} is not an array`);
    return v as T[];
  };
  const checks = arr<LedgerCheck>('checks');
  for (const c of checks) if (typeof c.id !== 'string' || (c.status !== 'PASS' && c.status !== 'FAIL')) throw new Error('ledger result: malformed check');
  const facts = arr<Fact>('facts');
  for (const f of facts) if (typeof f.id !== 'string' || typeof f.field !== 'string') throw new Error('ledger result: malformed fact');
  const metrics = (r.metrics ?? {}) as Partial<LedgerMetrics>;
  const m: LedgerMetrics = {
    facts: num(metrics.facts, facts.length),
    patient_facts: num(metrics.patient_facts, facts.filter((f) => f.source === 'patient').length),
    context_facts: num(metrics.context_facts, facts.filter((f) => f.source === 'context').length),
    reference_facts: num(metrics.reference_facts, facts.filter((f) => !isCaseFact(f)).length),
    cited_in_report: num(metrics.cited_in_report, 0),
    cited_agree: num(metrics.cited_agree, 0),
    cited_disagree: num(metrics.cited_disagree, 0),
    cited_unverifiable: num(metrics.cited_unverifiable, 0),
    thinking_chars: num(metrics.thinking_chars, 0),
    thinking_ids: num(metrics.thinking_ids, 0),
    thinking_fields: metrics.thinking_fields,
    candidates_named_in_thinking: metrics.candidates_named_in_thinking && typeof metrics.candidates_named_in_thinking === 'object' ? metrics.candidates_named_in_thinking : {},
    ignored: num(metrics.ignored, facts.filter((f) => f.ignored).length),
    ignored_informative: num(metrics.ignored_informative, facts.filter((f) => f.ignored && f.informative).length),
    checks_failed: num(metrics.checks_failed, checks.filter((c) => c.status === 'FAIL').length),
    checks_total: num(metrics.checks_total, checks.length),
  };
  const thinking = r.thinking && typeof r.thinking === 'object' ? r.thinking as Partial<LedgerThinking> : null;
  const rationale = r.rationale && typeof r.rationale === 'object' ? r.rationale as Partial<LedgerRationale> : null;
  const ablation = r.ablation && typeof r.ablation === 'object' ? r.ablation as Partial<LedgerAblation> : null;
  return {
    case_id: typeof r.case_id === 'string' ? r.case_id : null,
    truth: str(r.truth),
    decision: str(r.decision),
    candidates: arr<string>('candidates').filter((c) => typeof c === 'string'),
    checks,
    metrics: m,
    sections: arr<LedgerSection>('sections').map((s) => ({ title: String(s.title ?? ''), segments: (s.segments ?? []).map((seg) => ({ text: String(seg.text ?? ''), citation_ids: seg.citation_ids ?? [], cited: seg.cited ?? [], uncited_assertions: (seg.uncited_assertions ?? []).map(uncitedAssertion), informative: seg.informative !== false })) })),
    facts,
    thinking: thinking ? { text: String(thinking.text ?? ''), ids: thinking.ids ?? [], candidates: thinking.candidates ?? [] } : null,
    rationale: rationale ? {
      decision: str(rationale.decision), confidence: str(rationale.confidence),
      key_findings: rationale.key_findings ?? [], differential: (rationale.differential ?? []).map((d) => ({ ...d, supporting: d.supporting ?? [], contradicting: d.contradicting ?? [], criteria: d.criteria ?? [] })),
      discriminators: rationale.discriminators ?? [], unresolved: rationale.unresolved ?? [], would_change: rationale.would_change ?? [],
    } : null,
    ablation: ablation ? { removed_ids: ablation.removed_ids ?? [], decision_before: str(ablation.decision_before), decision_after: str(ablation.decision_after), changed: !!ablation.changed } : null,
  };
}
const num = (v: unknown, fallback: number) => (typeof v === 'number' && Number.isFinite(v) ? v : fallback);
const str = (v: unknown) => (typeof v === 'string' ? v : null);

// ---- grades --------------------------------------------------------------------------------------

/** Chip tone per citation grade. Tones are the stylesheet's status classes: agree green, disagree red, unverifiable amber,
 *  reference grey (neutral), not_found red outline (dashed), not_mentioned amber dashed (the fact's own value is "not mentioned"). */
export type GradeTone = 'good' | 'bad' | 'warn' | 'neutral' | 'bad outline' | 'warn outline';
export const GRADE_TONE: Record<CitationGrade, GradeTone> = {
  agree: 'good',
  disagree: 'bad',
  unverifiable: 'warn',
  reference: 'neutral',
  not_found: 'bad outline',
  not_mentioned: 'warn outline',
};
export const GRADE_ICON: Record<CitationGrade, string> = { agree: '✓', disagree: '✗', unverifiable: '?', reference: '§', not_found: '∅', not_mentioned: '–' };
export const GRADE_TEXT: Record<CitationGrade, string> = {
  agree: 'agrees with the ledger',
  disagree: 'disagrees with the ledger',
  unverifiable: 'could not be verified against the ledger',
  reference: 'reference criterion',
  not_found: 'no such fact in the ledger',
  not_mentioned: 'the fact is recorded as not mentioned',
};
export function gradeTone(grade: string | null | undefined): GradeTone {
  return GRADE_TONE[(grade ?? '') as CitationGrade] ?? 'neutral';
}
/** The CSS colour token a grade is drawn with (strip squares, legends). */
export function gradeColor(grade: string | null | undefined): string {
  switch (gradeTone(grade)) {
    case 'good': return 'var(--supported)';
    case 'bad': case 'bad outline': return 'var(--contradicted)';
    case 'warn': case 'warn outline': return 'var(--unsupported)';
    default: return 'var(--text-2)';
  }
}

// ---- thinking tokens -----------------------------------------------------------------------------

export type ThinkingToken =
  | { kind: 'text'; text: string }
  | { kind: 'id'; text: string; id: string; known: boolean }
  | { kind: 'candidate'; text: string; candidate: string };

/** Any `prefix_123` word is a fact id; `known` says whether the ledger has it. */
export const FACT_ID_RE = /\b([a-z]{1,3}_\d+)\b/g;

const escapeRe = (s: string) => s.replace(/[.*+?^${}()|[\]\\/]/g, '\\$&');

/** Split reasoning text into plain text, fact ids and candidate names so each can be rendered as a chip or highlight.
 *  Candidate names match whole words, case-insensitively, longest first; fact ids win over candidates at the same offset. */
export function tokeniseThinking(text: string, factIds: Iterable<string>, candidates: Iterable<string>): ThinkingToken[] {
  const known = new Set(factIds);
  const names = [...new Set([...candidates].filter((c) => c && c.trim()))].sort((a, b) => b.length - a.length);
  const canon = new Map(names.map((n) => [n.toLowerCase(), n] as const));
  const parts = ['([a-z]{1,3}_\\d+)'];
  if (names.length) parts.push(`(${names.map(escapeRe).join('|')})`);
  const re = new RegExp(`(?<![\\w/])(?:${parts.join('|')})(?![\\w/])`, 'gi');
  const out: ThinkingToken[] = [];
  let last = 0;
  for (const m of text.matchAll(re)) {
    const at = m.index ?? 0;
    if (at > last) out.push({ kind: 'text', text: text.slice(last, at) });
    if (m[1] !== undefined) {
      const id = m[1].toLowerCase();
      out.push({ kind: 'id', text: m[0], id, known: known.has(id) || known.has(m[0]) });
    } else {
      out.push({ kind: 'candidate', text: m[0], candidate: canon.get(m[0].toLowerCase()) ?? m[0] });
    }
    last = at + m[0].length;
  }
  if (last < text.length) out.push({ kind: 'text', text: text.slice(last) });
  return out;
}

/** How many times each candidate name is named in the text (whole-word, case-insensitive). */
export function candidateCounts(text: string, candidates: Iterable<string>): Record<string, number> {
  const counts: Record<string, number> = {};
  for (const c of candidates) counts[c] = 0;
  for (const t of tokeniseThinking(text, [], candidates)) if (t.kind === 'candidate') counts[t.candidate] = (counts[t.candidate] ?? 0) + 1;
  return counts;
}

// ---- coverage ------------------------------------------------------------------------------------

export type CoverageCategory = 'cited' | 'referenced' | 'ignored' | 'untested';
export const COVERAGE_META: Record<CoverageCategory, { text: string; description: string }> = {
  cited: { text: 'cited', description: 'Cited in the report or the rationale' },
  referenced: { text: 'referenced', description: 'Named in the thinking but not cited' },
  ignored: { text: 'ignored', description: 'Informative, yet never referenced or cited' },
  untested: { text: 'untested, ignored', description: 'Not informative (not performed / not mentioned) and never referenced' },
};
export const COVERAGE_ORDER: CoverageCategory[] = ['cited', 'referenced', 'ignored', 'untested'];

export function isCaseFact(f: Fact): boolean { return f.source === 'patient' || f.source === 'context'; }

export function coverageCategory(f: Fact): CoverageCategory {
  if (f.cited_in_report || f.cited_in_rationale) return 'cited';
  if (f.referenced_in_thinking) return 'referenced';
  return f.informative ? 'ignored' : 'untested';
}
export function coverageCounts(facts: Fact[]): Record<CoverageCategory, number> {
  const counts: Record<CoverageCategory, number> = { cited: 0, referenced: 0, ignored: 0, untested: 0 };
  for (const f of facts) if (isCaseFact(f)) counts[coverageCategory(f)]++;
  return counts;
}

// ---- ledger table --------------------------------------------------------------------------------

export type LedgerFilter = 'all' | 'ignored' | 'ignored_informative' | 'cited' | 'disagreements';
export const LEDGER_FILTERS: Array<[LedgerFilter, string]> = [
  ['all', 'All'], ['ignored', 'Ignored'], ['ignored_informative', 'Informative, ignored'], ['cited', 'Cited'], ['disagreements', 'Disagreements'],
];

/** Ids of facts cited with a disagreeing grade anywhere in the report. */
export function disagreeingIds(sections: LedgerSection[]): Set<string> {
  const out = new Set<string>();
  for (const s of sections) for (const seg of s.segments) for (const c of seg.cited) if (c.grade === 'disagree') out.add(c.id);
  return out;
}

export function filterFacts(facts: Fact[], filter: LedgerFilter, search: string, disagreeing: Set<string>): Fact[] {
  const q = search.trim().toLowerCase();
  return facts.filter((f) => {
    switch (filter) {
      case 'ignored': if (!f.ignored) return false; break;
      case 'ignored_informative': if (!(f.ignored && f.informative)) return false; break;
      case 'cited': if (!(f.cited_in_report || f.cited_in_rationale)) return false; break;
      case 'disagreements': if (!disagreeing.has(f.id)) return false; break;
    }
    if (!q) return true;
    return [f.id, f.field, f.value, f.evidence, f.section, f.source, f.candidate ?? ''].some((v) => String(v ?? '').toLowerCase().includes(q));
  });
}

export interface FactGroup { source: string; section: string; facts: Fact[] }
/** Group in ledger order: by source, then by section, first appearance wins. */
export function groupFacts(facts: Fact[]): FactGroup[] {
  const groups: FactGroup[] = [];
  const index = new Map<string, FactGroup>();
  for (const f of facts) {
    const key = `${f.source}\u0000${f.section}`;
    let g = index.get(key);
    if (!g) { g = { source: f.source, section: f.section, facts: [] }; index.set(key, g); groups.push(g); }
    g.facts.push(f);
  }
  return groups;
}

export const SOURCE_TEXT: Record<string, string> = { patient: 'Patient', context: 'Clinical context', who: 'Reference (WHO)', reference: 'Reference' };
export function sourceText(source: string): string { return SOURCE_TEXT[source] ?? source; }

export function factMap(facts: Fact[]): Map<string, Fact> { return new Map(facts.map((f) => [f.id, f])); }

/** `id · field = value` for a chip label; falls back to the id alone for unknown ids. */
export function factLabel(id: string, f: { field?: string | null; value?: string | null } | undefined): string {
  if (!f || !f.field) return id;
  return `${id} · ${f.field} = ${f.value ?? '—'}`;
}

/** Older results carried uncited assertions as plain strings; keep them renderable. */
export function uncitedAssertion(a: unknown): UncitedAssertion {
  if (typeof a === 'string') return { field: a, grade: 'unknown' };
  const o = (a ?? {}) as Record<string, unknown>;
  return { field: String(o.field ?? ''), stated: o.stated == null ? null : String(o.stated), fact_id: o.fact_id == null ? null : String(o.fact_id), value: o.value == null ? null : String(o.value), grade: String(o.grade ?? 'unknown') };
}

export function describeUncited(a: UncitedAssertion): string {
  const what = a.stated ? `${a.field}: ${a.stated}` : a.field;
  const against = a.fact_id ? ` vs ${a.fact_id} (${a.value ?? '?'})` : '';
  return `${what}${against}`;
}
