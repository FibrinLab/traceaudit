// Typed client for the `traceaudit serve` HTTP API (specs/17-service.md §3).
// No React here so it can be unit-tested with a stubbed fetch.
import type { LexiconEntity, LexiconFinding, Polarity, Reports, Section } from '../types';
import { parseLedgerResult, type LedgerRequest, type LedgerResult } from './ledger';
import { parseAnalyseResponse, type AnalyseResponse } from './analyse';
export type { Reports };
export type { LedgerRequest, LedgerResult };
export type { AnalyseResponse, AnalyseDocument, AnalyseLexicon, AnalyseAnswer } from './analyse';

export interface ApiSettings {
  /** Origin or prefix of the service, e.g. `http://127.0.0.1:8080`. Empty means same origin. */
  base: string;
  /** Bearer token; sent as `Authorization: Bearer …` when non-empty. Never placed in a URL. */
  token: string;
}

export const API_SETTINGS_KEY = 'traceaudit:api';
export const DEFAULT_API_SETTINGS: ApiSettings = { base: '', token: '' };

export interface StorageLike { getItem(k: string): string | null; setItem(k: string, v: string): void }

export function loadApiSettings(storage: StorageLike | null = defaultStorage()): ApiSettings {
  try {
    const raw = storage?.getItem(API_SETTINGS_KEY);
    if (!raw) return DEFAULT_API_SETTINGS;
    const parsed = JSON.parse(raw) as Partial<ApiSettings>;
    return { base: typeof parsed.base === 'string' ? parsed.base : '', token: typeof parsed.token === 'string' ? parsed.token : '' };
  } catch { return DEFAULT_API_SETTINGS; }
}
export function saveApiSettings(s: ApiSettings, storage: StorageLike | null = defaultStorage()): void {
  try { storage?.setItem(API_SETTINGS_KEY, JSON.stringify({ base: normaliseBase(s.base), token: s.token })); } catch { /* storage unavailable */ }
}
function defaultStorage(): StorageLike | null {
  try { return typeof localStorage !== 'undefined' ? localStorage : null; } catch { return null; }
}

/** Trim and drop a trailing slash so `${base}/api/…` joins cleanly. */
export function normaliseBase(base: string): string {
  return base.trim().replace(/\/+$/, '');
}

// ---- response types -------------------------------------------------------------------------------

/** Per-workspace limits reported by the service when it runs jobs on its own (operator) keys. */
export interface Limits {
  max_calls_per_job: number;
  max_calls_per_day: number;
  calls_used_today: number;
  operator_keys: string[];
}
export interface Health {
  version: string;
  /** Version of the operator-configured lexicon, when there is one; the service ships none. */
  lexicon_version?: string | null;
  modes: string[];
  clients: string[];
  anonymous: string;
  workspace: string;
  /** Client kinds that can run on the site's own key; the key field is hidden for these. Older services omit it. */
  operator_keys?: string[];
  limits?: Limits;
  /** Domain and document sections of the operator-configured lexicon; `null` / `[]` when none is configured. */
  domain?: string | null;
  sections?: Section[];
}
/** Calls left in today's operator-key budget, or null when the service reports no limits. */
export function budgetRemaining(h: Health | null | undefined): number | null {
  if (!h?.limits) return null;
  return Math.max(0, h.limits.max_calls_per_day - h.limits.calls_used_today);
}
/** The default client kind: the first operator-key kind if any, else `sim`, else the first allowed kind. */
export function defaultClientKind(h: Health): string {
  return h.operator_keys?.find((k) => h.clients.includes(k)) ?? (h.clients.includes('sim') ? 'sim' : h.clients[0] ?? '');
}
export interface LexiconDisplay { version: string; entities: LexiconEntity[]; findings: LexiconFinding[]; domain?: string; sections?: Section[] }
/** One row of `GET /api/lexicons`: the starter lexicons the service ships as examples (`source: "example"`, ids like
 *  `example:incident-triage`) and the workspace's uploads (`source: "upload"`). There is no default lexicon. */
export interface LexiconMeta { id: string; name?: string | null; domain: string; version: string; sections: Section[]; n_findings: number; n_entities: number; source: 'example' | 'upload' | string }
/** Human label for a lexicon row: "Incident triage (example)", "Ops (uploaded)". */
export function lexiconLabel(l: LexiconMeta): string {
  const base = (l.name && l.name !== l.domain ? l.name : titleFromDomain(l.domain)) || l.id;
  return `${base} (${l.source === 'upload' ? 'uploaded' : l.source})`;
}
export function titleFromDomain(d: string): string {
  const s = d.replace(/[_-]+/g, ' ').trim();
  return s ? s[0].toUpperCase() + s.slice(1) : s;
}
export interface CaseSet { id: string; name: string; n_cases: number; n_perturbations: number; approved: boolean; source: string; /** Not sent by the service yet; shown when present. */ domain?: string | null }
/** Body of `POST /api/uploads`: a named case set as JSONL text (one case or perturbation per line). */
export interface UploadCreate { name: string; cases: string; approved: boolean }

export interface AnalyseRequest {
  /** `{ <section id>: text }` for the chosen lexicon's sections, with display titles. */
  documents?: Record<string, string>;
  titles?: Record<string, string>;
  reasoning: string;
  answer: string;
  truth?: Record<string, Polarity>;
  entity?: string;
  /** An example or uploaded lexicon id. The service has no default: without a usable id it answers `lexicon_required`. */
  lexicon_id?: string;
}
// The response is a fact-ledger result (`LedgerResult`) plus `documents` with each fact's evidence span; see lib/analyse.ts.

export type JobStatus = 'queued' | 'running' | 'scoring' | 'exporting' | 'done' | 'failed' | 'cancelled' | 'interrupted';
export const TERMINAL_STATUSES: ReadonlySet<JobStatus> = new Set<JobStatus>(['done', 'failed', 'cancelled', 'interrupted']);
export function isTerminal(status: JobStatus | string | null | undefined): boolean { return !!status && TERMINAL_STATUSES.has(status as JobStatus); }

export interface JobProgress { done: number; total: number; ok?: number; errors?: number; eta_s?: number | null }
export interface JobClient { kind: string; endpoint?: string | null; model?: string | null; api_key?: string | null }
export interface JobCreate {
  mode: 'audit';
  client: JobClient;
  case_set: string;
  efforts: string[];
  runs: number;
  variants?: string[];
  seed?: number;
  rule?: string;
  judge?: false;
  notes?: string;
}
export interface JobHeadline { traces?: number | null; errors?: number | null; grounding_rate?: number | null; silent_rate?: number | null; spurious_rate?: number | null; silent_shift_rate?: number | null }
export interface JobSummary { job_id: string; status: JobStatus; created: string; progress: JobProgress | null; summary_headline?: string | null; headline?: JobHeadline | string | null }

/** The service reports the headline as an object of rates; older mocks sent a sentence. Render either. */
export function formatHeadline(h: JobHeadline | string | null | undefined): string | null {
  if (h == null) return null;
  if (typeof h === 'string') return h;
  const pct = (v: number | null | undefined) => (v == null ? 'n/a' : `${Math.round(v * 100)}%`);
  const parts = [`grounding ${pct(h.grounding_rate)}`];
  if (h.silent_rate != null) parts.push(`silent ${pct(h.silent_rate)}`);
  if (h.spurious_rate != null) parts.push(`spurious ${pct(h.spurious_rate)}`);
  if (h.silent_shift_rate != null) parts.push(`silent shift ${pct(h.silent_shift_rate)}`);
  const n = h.traces != null ? ` across ${h.traces} traces` : '';
  const e = h.errors ? `, ${h.errors} error${h.errors === 1 ? '' : 's'}` : '';
  return parts.join(', ') + n + e;
}
export interface Job {
  job_id: string;
  status: JobStatus;
  created: string;
  started: string | null;
  finished: string | null;
  progress: JobProgress | null;
  config: Omit<JobCreate, 'client'> & { client: Omit<JobClient, 'api_key'> };
  error?: string | null;
  headline?: JobHeadline | string | null;
}

export const JOB_FILES = ['summary.json', 'report.md', 'traces.jsonl', 'long.csv', 'manifest.json'] as const;
export type JobFile = (typeof JOB_FILES)[number];

// ---- errors ----------------------------------------------------------------------------------------

export class ApiError extends Error {
  constructor(public readonly status: number, public readonly code: string, message: string) {
    super(message);
    this.name = 'ApiError';
  }
}

/** Parse `{ error: { code, message } }`; fall back to the status text for anything else. */
export async function errorFromResponse(res: Response): Promise<ApiError> {
  let code = `http_${res.status}`;
  let message = `${res.status} ${res.statusText || 'error'}`.trim();
  try {
    const text = await res.text();
    try {
      const body = JSON.parse(text) as { error?: { code?: unknown; message?: unknown } };
      if (body && body.error && typeof body.error === 'object') {
        if (typeof body.error.code === 'string') code = body.error.code;
        if (typeof body.error.message === 'string') message = body.error.message;
      } else if (text) message = text.slice(0, 300);
    } catch { if (text) message = text.slice(0, 300); }
  } catch { /* unreadable body */ }
  return new ApiError(res.status, code, message);
}

/** Plain-language wording for the service's job-limit error codes; other codes fall through to the service's message. */
export const PLAIN_ERRORS: Record<string, string> = {
  key_required: 'This client kind needs your own API key on this site; the site does not run it on its key. Enter a key, or choose a client kind that runs on the site\'s key.',
  job_too_large: 'This job asks for more model calls than the site allows in one job. Choose fewer efforts, fewer runs or a smaller case set.',
  budget_exhausted: 'The site\'s daily budget for its own key is used up. Try again tomorrow, or run the job on your own key.',
  bad_lexicon: 'That file is not a lexicon the service can load. It needs version, domain, sections, entities and findings; see examples/lexicon-incident-triage.json.',
  lexicon_not_found: 'The chosen lexicon is no longer on the service. Pick another one or upload it again.',
  lexicon_required: 'Choose a lexicon first. The service has no default: pick an example or upload your own.',
};

export function describeError(e: unknown): string {
  if (e instanceof ApiError) return PLAIN_ERRORS[e.code] ?? e.message;
  if (e instanceof TypeError) return `Could not reach the service (${e.message}). Check the API base URL in Settings.`;
  return e instanceof Error ? e.message : String(e);
}

// ---- client ----------------------------------------------------------------------------------------

export interface ApiClient {
  settings: ApiSettings;
  url: (path: string) => string;
  headers: (extra?: Record<string, string>) => Record<string, string>;
  health: () => Promise<Health>;
  /** One lexicon's display data, by example or upload id. */
  lexicon: (id: string) => Promise<LexiconDisplay>;
  lexicons: () => Promise<LexiconMeta[]>;
  /** Upload a lexicon JSON document (the file's text); resolves to its metadata, which includes the new id. */
  uploadLexicon: (lexiconJson: string, name?: string) => Promise<LexiconMeta>;
  caseSets: () => Promise<CaseSet[]>;
  /** Upload a case set (JSONL text); resolves to the new case set as `/api/case-sets` lists it. */
  createUpload: (req: UploadCreate) => Promise<CaseSet>;
  /** Analyse one free-text trace against its documents; resolves to a ledger result with the documents' fact spans. */
  analyse: (req: AnalyseRequest) => Promise<AnalyseResponse>;
  /** Audit a structured trace artefact (`{markdown}` or `{case, trace}`) against its fact ledger. No model is called. */
  auditLedger: (req: LedgerRequest) => Promise<LedgerResult>;
  createJob: (req: JobCreate) => Promise<{ job_id: string }>;
  listJobs: () => Promise<JobSummary[]>;
  getJob: (id: string) => Promise<Job>;
  cancelJob: (id: string) => Promise<Job | null>;
  resumeJob: (id: string, apiKey?: string) => Promise<{ job_id: string }>;
  bundleUrl: (id: string) => string;
  fileUrl: (id: string, name: JobFile) => string;
  fetchFile: (id: string, name: JobFile) => Promise<Blob>;
}

export function authHeaders(settings: ApiSettings, extra: Record<string, string> = {}): Record<string, string> {
  const h: Record<string, string> = { Accept: 'application/json', ...extra };
  if (settings.token) h.Authorization = `Bearer ${settings.token}`;
  return h;
}

export function createApi(settings: ApiSettings, fetchImpl: typeof fetch = (...a) => fetch(...a)): ApiClient {
  const base = normaliseBase(settings.base);
  const url = (path: string) => `${base}${path.startsWith('/') ? path : '/' + path}`;
  const headers = (extra: Record<string, string> = {}) => authHeaders(settings, extra);

  async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const res = await fetchImpl(url(path), { ...init, headers: headers(init.headers as Record<string, string> | undefined), cache: 'no-store' });
    if (!res.ok) throw await errorFromResponse(res);
    if (res.status === 204) return undefined as T;
    return (await res.json()) as T;
  }
  const json = (body: unknown): RequestInit => ({ method: 'POST', body: JSON.stringify(body), headers: { 'Content-Type': 'application/json' } });

  return {
    settings: { base, token: settings.token },
    url,
    headers,
    health: () => request<Health>('/api/health'),
    lexicon: (id) => request<LexiconDisplay>(`/api/lexicon?id=${encodeURIComponent(id)}`),
    lexicons: () => request<LexiconMeta[]>('/api/lexicons'),
    uploadLexicon: (lexiconJson, name) => request<LexiconMeta>('/api/lexicons', json(name ? { lexicon: lexiconJson, name } : { lexicon: lexiconJson })),
    caseSets: () => request<CaseSet[]>('/api/case-sets'),
    createUpload: (req) => request<CaseSet>('/api/uploads', json(req)),
    analyse: async (req) => parseAnalyseResponse(await request<unknown>('/api/analyse', json(req))),
    auditLedger: async (req) => parseLedgerResult(await request<unknown>('/api/ledger', json(req))),
    createJob: (req) => request<{ job_id: string }>('/api/jobs', json(req)),
    listJobs: () => request<JobSummary[]>('/api/jobs'),
    getJob: (id) => request<Job>(`/api/jobs/${encodeURIComponent(id)}`),
    cancelJob: (id) => request<Job | null>(`/api/jobs/${encodeURIComponent(id)}`, { method: 'DELETE' }),
    resumeJob: (id, apiKey) => request<{ job_id: string }>(`/api/jobs/${encodeURIComponent(id)}/resume`, json(apiKey ? { api_key: apiKey } : {})),
    bundleUrl: (id) => url(`/api/jobs/${encodeURIComponent(id)}/bundle/`),
    fileUrl: (id, name) => url(`/api/jobs/${encodeURIComponent(id)}/files/${name}`),
    fetchFile: async (id, name) => {
      const res = await fetchImpl(url(`/api/jobs/${encodeURIComponent(id)}/files/${name}`), { headers: headers({ Accept: '*/*' }), cache: 'no-store' });
      if (!res.ok) throw await errorFromResponse(res);
      return res.blob();
    },
  };
}
