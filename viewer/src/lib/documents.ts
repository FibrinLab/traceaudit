// Document sections: which source documents a case has, in what order, under which titles.
// A lexicon declares `sections`; the service echoes them as `case.sections`. A bundle that carries no sections
// falls back to the document keys themselves, humanised. Nothing in the viewer assumes a particular set of documents.
import type { Reports, Section } from '../types';
import type { AnalyseRequest } from './api';

/** A readable title for a section id with no declared title: `deploy_history` → `Deploy history`. */
export function titleFromId(id: string): string {
  const s = id.replace(/[_-]+/g, ' ').trim();
  return s ? s[0].toUpperCase() + s.slice(1) : id;
}

/** The sections of a case: the declared ones when present (plus any extra document keys, in key order), else the
 *  document keys in their own order. Empty only when there are neither declared sections nor documents. */
export function sectionsFor(reports: Partial<Reports> | null | undefined, declared?: Section[] | null): Section[] {
  const keys = Object.keys(reports ?? {});
  const out: Section[] = [];
  const seen = new Set<string>();
  if (declared?.length) {
    for (const s of declared) { if (!seen.has(s.id)) { out.push({ id: s.id, title: s.title || titleFromId(s.id) }); seen.add(s.id); } }
  }
  for (const k of keys) if (!seen.has(k)) { out.push({ id: k, title: titleFromId(k) }); seen.add(k); }
  return out;
}

export function sectionTitle(sections: Section[] | null | undefined, id: string): string {
  return sections?.find((s) => s.id === id)?.title ?? titleFromId(id);
}

/** Position of a section id in the case's order (unknown ids sort last). */
export function sectionIndex(sections: Section[] | null | undefined, id: string): number {
  const i = sections?.findIndex((s) => s.id === id) ?? -1;
  return i < 0 ? Number.MAX_SAFE_INTEGER : i;
}

export interface AnalyseInputs {
  /** Section id → text, in the lexicon's section order. Empty documents are kept so the order and titles survive. */
  documents: Record<string, string>;
  sections: Section[];
  reasoning: string;
  answer: string;
  entity?: string;
  /** The chosen lexicon; the service has no default, so the form requires one. */
  lexiconId?: string;
  truth?: AnalyseRequest['truth'];
}

/** The general `/api/analyse` body: `documents` + `titles` + `lexicon_id` (+ `entity`, `truth` when given). */
export function buildAnalyseRequest(inp: AnalyseInputs): AnalyseRequest {
  const documents: Record<string, string> = {};
  const titles: Record<string, string> = {};
  for (const s of inp.sections) { documents[s.id] = inp.documents[s.id] ?? ''; titles[s.id] = s.title; }
  for (const [k, v] of Object.entries(inp.documents)) if (!(k in documents)) { documents[k] = v; titles[k] = titleFromId(k); }
  const req: AnalyseRequest = { documents, titles, reasoning: inp.reasoning, answer: inp.answer };
  if (inp.entity) req.entity = inp.entity;
  if (inp.lexiconId) req.lexicon_id = inp.lexiconId;
  if (inp.truth && Object.keys(inp.truth).length) req.truth = inp.truth;
  return req;
}

/** True when at least one document has text. */
export function hasAnyDocument(documents: Record<string, string>): boolean {
  return Object.values(documents).some((v) => v.trim().length > 0);
}
