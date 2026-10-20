import type { Bundle, BundleIndex, CaseFile } from '../types';

export const SUPPORTED_BUNDLE_VERSION = 1;

export class BundleError extends Error {}

/** Minimal structural validation of index.json so a wrong file fails loudly. */
export function validateIndex(x: unknown): BundleIndex {
  if (!x || typeof x !== 'object') throw new BundleError('index.json is not an object');
  const idx = x as Partial<BundleIndex>;
  if (typeof idx.bundle_version !== 'number') throw new BundleError('index.json lacks bundle_version');
  if (idx.bundle_version > SUPPORTED_BUNDLE_VERSION) {
    throw new BundleError(`bundle_version ${idx.bundle_version} is newer than this viewer supports (${SUPPORTED_BUNDLE_VERSION})`);
  }
  if (!idx.run || typeof idx.run.run_id !== 'string') throw new BundleError('index.json lacks run.run_id');
  if (!Array.isArray(idx.cases)) throw new BundleError('index.json lacks cases[]');
  if (!idx.rubric || !Array.isArray(idx.rubric.dimensions)) throw new BundleError('index.json lacks rubric');
  if (!idx.summary) throw new BundleError('index.json lacks summary');
  return {
    ...(idx as BundleIndex),
    study: idx.study ?? null,
    ratings: idx.ratings ?? null,
  };
}

export function validateCaseFile(x: unknown, caseId: string): CaseFile {
  if (!x || typeof x !== 'object') throw new BundleError(`case file ${caseId} is not an object`);
  const cf = x as Partial<CaseFile>;
  if (!cf.case || !cf.variants || !Array.isArray(cf.traces)) throw new BundleError(`case file ${caseId} is missing case/variants/traces`);
  return cf as CaseFile;
}

function joinUrl(base: string, rel: string): string {
  const b = base.endsWith('/') ? base : base + '/';
  return b + rel.replace(/^\.?\//, '');
}

async function fetchJson(url: string, init: RequestInit = {}): Promise<unknown> {
  const res = await fetch(url, { cache: 'no-cache', ...init });
  if (!res.ok) throw new BundleError(await describeHttpError(res, url));
  return res.json();
}

/** Prefer the service's `{ error: { message } }` when present; otherwise `HTTP <status> loading <url>`. */
async function describeHttpError(res: Response, url: string): Promise<string> {
  try {
    const body = (await res.json()) as { error?: { message?: unknown } };
    if (body?.error && typeof body.error.message === 'string') return `${body.error.message} (HTTP ${res.status} loading ${url})`;
  } catch { /* not JSON */ }
  return `HTTP ${res.status} loading ${url}`;
}

function makeBundle(index: BundleIndex, source: string, loader: (entry: { case_id: string; file: string }) => Promise<unknown>): Bundle {
  const cases = new Map<string, CaseFile>();
  const pending = new Map<string, Promise<CaseFile>>();
  const byId = new Map(index.cases.map((c) => [c.case_id, c]));
  const loadCase = (caseId: string): Promise<CaseFile> => {
    const have = cases.get(caseId);
    if (have) return Promise.resolve(have);
    const inflight = pending.get(caseId);
    if (inflight) return inflight;
    const entry = byId.get(caseId);
    if (!entry) return Promise.reject(new BundleError(`Unknown case ${caseId}`));
    const p = loader(entry)
      .then((raw) => validateCaseFile(raw, caseId))
      .then((cf) => { cases.set(caseId, cf); pending.delete(caseId); return cf; })
      .catch((e) => { pending.delete(caseId); throw e; });
    pending.set(caseId, p);
    return p;
  };
  return { index, cases, loadCase, source };
}

/** Load a sharded bundle (index.json + cases/) or a single bundle.json from a URL.
 *  `init` (e.g. an Authorization header for a service-hosted job bundle) is sent with every request. */
export async function loadBundleFromUrl(url: string, init: RequestInit = {}): Promise<Bundle> {
  if (/\.json$/i.test(url)) {
    const raw = await fetchJson(url, init);
    return bundleFromSingleObject(raw, url);
  }
  const raw = await fetchJson(joinUrl(url, 'index.json'), init);
  const index = validateIndex(raw);
  return makeBundle(index, url, (entry) => fetchJson(joinUrl(url, entry.file), init));
}

/** Un-sharded `bundle.json`: `{ index: {...}, cases: { "<case_id>": {...} } }`. */
export function bundleFromSingleObject(raw: unknown, source: string): Bundle {
  if (!raw || typeof raw !== 'object') throw new BundleError('bundle.json is not an object');
  const obj = raw as { index?: unknown; cases?: Record<string, unknown> };
  if (!obj.index || !obj.cases) throw new BundleError('bundle.json must contain `index` and `cases`');
  const index = validateIndex(obj.index);
  const cases = obj.cases;
  const b = makeBundle(index, source, (entry) => {
    const c = cases[entry.case_id];
    return c ? Promise.resolve(c) : Promise.reject(new BundleError(`bundle.json lacks case ${entry.case_id}`));
  });
  return b;
}

/** Load from a set of File objects (folder picker or single bundle.json). */
export async function loadBundleFromFiles(files: File[]): Promise<Bundle> {
  const byRel = new Map<string, File>();
  for (const f of files) {
    const rel = ((f as File & { webkitRelativePath?: string }).webkitRelativePath || f.name).replace(/\\/g, '/');
    byRel.set(rel, f);
  }
  const single = files.find((f) => /bundle\.json$/i.test(f.name));
  if (files.length === 1 && single) {
    return bundleFromSingleObject(JSON.parse(await single.text()), single.name);
  }
  const indexFile = files.find((f) => f.name === 'index.json');
  if (!indexFile) {
    if (single) return bundleFromSingleObject(JSON.parse(await single.text()), single.name);
    throw new BundleError('No index.json or bundle.json found in the selected files');
  }
  const indexRel = ((indexFile as File & { webkitRelativePath?: string }).webkitRelativePath || indexFile.name).replace(/\\/g, '/');
  const root = indexRel.slice(0, indexRel.length - 'index.json'.length);
  const index = validateIndex(JSON.parse(await indexFile.text()));
  return makeBundle(index, root || indexFile.name, async (entry) => {
    const rel = root + entry.file.replace(/^\.?\//, '');
    const f = byRel.get(rel) ?? [...byRel.values()].find((x) => x.name === entry.file.split('/').pop());
    if (!f) throw new BundleError(`Case file ${entry.file} not among the selected files`);
    return JSON.parse(await f.text());
  });
}

/** File System Access API (Chromium): pick a directory handle. */
export async function loadBundleFromDirectoryHandle(dir: FileSystemDirectoryHandle): Promise<Bundle> {
  const indexHandle = await dir.getFileHandle('index.json');
  const index = validateIndex(JSON.parse(await (await indexHandle.getFile()).text()));
  return makeBundle(index, dir.name, async (entry) => {
    const parts = entry.file.replace(/^\.?\//, '').split('/');
    let cur: FileSystemDirectoryHandle = dir;
    for (const p of parts.slice(0, -1)) cur = await cur.getDirectoryHandle(p);
    const fh = await cur.getFileHandle(parts[parts.length - 1]);
    return JSON.parse(await (await fh.getFile()).text());
  });
}

/** The `?bundle=<url>` parameter, or null when the address names no bundle (nothing is packaged with the viewer). */
export function bundleUrlFromLocation(search: string = window.location.search): string | null {
  const params = new URLSearchParams(search);
  return params.get('bundle') || null;
}
