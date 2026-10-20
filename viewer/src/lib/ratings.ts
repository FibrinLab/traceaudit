import type { RatingRecord } from '../types';

export const DIMENSIONS = ['D1', 'D2', 'D3', 'D4', 'D5', 'D6', 'D7'] as const;
export type DimensionId = (typeof DIMENSIONS)[number];

export interface TraceRating {
  trace_key: string;
  presentation_index: number;
  scores: Partial<Record<DimensionId, number>>;
  error_tags: string[];
  comment: string;
  started_at: string | null;
  submitted_at: string | null;
  /** accumulated active time in ms */
  duration_ms: number;
}

export interface RaterSession {
  rater_id: string;
  study_id: string;
  session_id: string;
  order: string[];
  started_at: string;
}

export interface RatingState {
  session: RaterSession;
  ratings: Record<string, TraceRating>; // by trace_key
}

export const RATER_ID_RE = /^R\d{2}$/;

export function storageKey(runId: string, studyId: string, raterId: string): string {
  return `traceaudit:ratings:${runId}:${studyId}:${raterId}`;
}

export function settingsKey(runId: string): string {
  return `traceaudit:settings:${runId}`;
}

export interface StorageLike { getItem(k: string): string | null; setItem(k: string, v: string): void; removeItem(k: string): void }

export function loadRatingState(storage: StorageLike, runId: string, studyId: string, raterId: string): RatingState | null {
  const raw = storage.getItem(storageKey(runId, studyId, raterId));
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as RatingState;
    if (!parsed.session || !parsed.ratings) return null;
    return parsed;
  } catch {
    return null;
  }
}

export function saveRatingState(storage: StorageLike, runId: string, state: RatingState): void {
  storage.setItem(storageKey(runId, state.session.study_id, state.session.rater_id), JSON.stringify(state));
}

export function newSessionId(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) return crypto.randomUUID();
  // Fallback: RFC 4122-ish v4 from Math.random
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    return (c === 'x' ? r : (r & 0x3) | 0x8).toString(16);
  });
}

export function emptyTraceRating(traceKey: string, presentationIndex: number, now: string): TraceRating {
  return { trace_key: traceKey, presentation_index: presentationIndex, scores: {}, error_tags: [], comment: '', started_at: now, submitted_at: null, duration_ms: 0 };
}

export function isComplete(r: TraceRating | undefined): boolean {
  if (!r) return false;
  return DIMENSIONS.every((d) => typeof r.scores[d] === 'number') && r.error_tags.length > 0;
}

/** Apply the `none` exclusivity rule to a tag toggle. */
export function toggleTag(tags: string[], tag: string): string[] {
  if (tag === 'none') return tags.includes('none') ? [] : ['none'];
  const without = tags.filter((t) => t !== 'none');
  return without.includes(tag) ? without.filter((t) => t !== tag) : [...without, tag];
}

export interface ExportMeta { viewer_version: string; bundle_run_id: string }

/** One record per scored dimension plus one `tags` record (spec 12 §5). Incomplete traces are skipped unless includeIncomplete. */
export function ratingRecords(state: RatingState, meta: ExportMeta, includeIncomplete = false): RatingRecord[] {
  const out: RatingRecord[] = [];
  const { session } = state;
  for (const r of Object.values(state.ratings)) {
    if (!includeIncomplete && !isComplete(r)) continue;
    const submitted = r.submitted_at ?? new Date().toISOString();
    const base = {
      schema_version: 1 as const,
      study_id: session.study_id,
      rater_id: session.rater_id,
      session_id: session.session_id,
      trace_key: r.trace_key,
      presentation_index: r.presentation_index,
      started_at: r.started_at,
      submitted_at: submitted,
      duration_ms: Math.round(r.duration_ms),
      blinded: true,
      viewer_version: meta.viewer_version,
      bundle_run_id: meta.bundle_run_id,
    };
    for (const d of DIMENSIONS) {
      const score = r.scores[d];
      if (typeof score !== 'number') continue;
      out.push({ ...base, dimension: d, score, error_tags: null, comment: null });
    }
    if (r.error_tags.length > 0 || r.comment) {
      out.push({ ...base, dimension: 'tags', score: null, error_tags: r.error_tags.slice(), comment: r.comment ? r.comment : null });
    }
  }
  return out;
}

export function toJsonl(records: RatingRecord[]): string {
  return records.map((r) => JSON.stringify(r)).join('\n') + (records.length ? '\n' : '');
}

export function exportFilename(studyId: string, raterId: string): string {
  return `ratings-${studyId}-${raterId}.jsonl`;
}

/** Validate a record against the shape in ratings-schema.json (structural subset, no external library). */
export function validateRecord(r: RatingRecord): string[] {
  const errs: string[] = [];
  if (r.schema_version !== 1) errs.push('schema_version must be 1');
  if (typeof r.study_id !== 'string') errs.push('study_id missing');
  if (!RATER_ID_RE.test(r.rater_id)) errs.push('rater_id must match ^R\\d{2}$');
  if (typeof r.trace_key !== 'string') errs.push('trace_key missing');
  if (![...DIMENSIONS, 'tags'].includes(r.dimension)) errs.push(`dimension ${r.dimension} not allowed`);
  if (r.score !== null && (!Number.isInteger(r.score) || r.score < 1 || r.score > 4)) errs.push('score must be an integer 1–4 or null');
  if (r.error_tags !== null && !Array.isArray(r.error_tags)) errs.push('error_tags must be an array or null');
  if (typeof r.submitted_at !== 'string') errs.push('submitted_at missing');
  if (typeof r.blinded !== 'boolean') errs.push('blinded must be boolean');
  if (r.dimension === 'tags' && r.score !== null) errs.push('tags record must have score null');
  if (r.dimension !== 'tags' && r.error_tags !== null) errs.push('dimension record must have error_tags null');
  return errs;
}
