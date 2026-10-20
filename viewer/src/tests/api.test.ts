import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiError, budgetRemaining, createApi, defaultClientKind, describeError, errorFromResponse, loadApiSettings, normaliseBase, saveApiSettings, type Health, type StorageLike } from '../lib/api';

function fetchStub(handler: (url: string, init: RequestInit) => Response | Promise<Response>) {
  const calls: Array<{ url: string; init: RequestInit }> = [];
  const fn = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
    calls.push({ url, init: init ?? {} });
    return handler(url, init ?? {});
  });
  return { fn: fn as unknown as typeof fetch, calls };
}
const ok = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });

afterEach(() => vi.unstubAllGlobals());

describe('createApi', () => {
  it('joins the base URL and sends the bearer header only when a token is set', async () => {
    const { fn, calls } = fetchStub(() => ok({ version: '0.2.0', lexicon_version: null, modes: [], clients: ['sim'], anonymous: 'analyse', workspace: 'public', domain: null, sections: [] }));
    const withToken = createApi({ base: 'http://127.0.0.1:8080/', token: 'abc' }, fn);
    const h = await withToken.health();
    expect(h.version).toBe('0.2.0');
    expect(h.domain).toBeNull();
    expect(h.sections).toEqual([]);
    expect(calls[0].url).toBe('http://127.0.0.1:8080/api/health');
    expect((calls[0].init.headers as Record<string, string>).Authorization).toBe('Bearer abc');

    const anonymous = createApi({ base: '', token: '' }, fn);
    await anonymous.caseSets();
    expect(calls[1].url).toBe('/api/case-sets');
    expect((calls[1].init.headers as Record<string, string>).Authorization).toBeUndefined();
  });

  it('never puts the token in a URL', () => {
    const api = createApi({ base: 'http://h', token: 'secret' });
    expect(api.bundleUrl('j1')).toBe('http://h/api/jobs/j1/bundle/');
    expect(api.fileUrl('j1', 'summary.json')).toBe('http://h/api/jobs/j1/files/summary.json');
    expect(api.url('/api/jobs')).not.toContain('secret');
  });

  it('posts JSON bodies and accepts 202 for job creation', async () => {
    const { fn, calls } = fetchStub((url) => url.endsWith('/api/jobs') ? ok({ job_id: 'job-1' }, 202) : ok({}));
    const api = createApi({ base: '', token: 't' }, fn);
    const r = await api.createJob({ mode: 'audit', client: { kind: 'sim', model: 'simulated' }, case_set: 'sample', efforts: ['low'], runs: 1 });
    expect(r.job_id).toBe('job-1');
    expect(calls[0].init.method).toBe('POST');
    expect((calls[0].init.headers as Record<string, string>)['Content-Type']).toBe('application/json');
    expect(JSON.parse(calls[0].init.body as string)).toMatchObject({ mode: 'audit', case_set: 'sample' });
    await api.cancelJob('job 1');
    expect(calls[1].init.method).toBe('DELETE');
    expect(calls[1].url).toBe('/api/jobs/job%201');
  });

  it('addresses lexicons by id and posts case-set uploads', async () => {
    const { fn, calls } = fetchStub((url) => url.endsWith('/api/uploads') ? ok({ id: 'up-1', name: 'Ops cases', n_cases: 2, n_perturbations: 1, approved: true, source: 'upload' }, 201) : ok({ version: '0.1.0', entities: [], findings: [] }));
    const api = createApi({ base: '', token: '' }, fn);
    await api.lexicon('example:incident-triage');
    expect(calls[0].url).toBe('/api/lexicon?id=example%3Aincident-triage');
    const set = await api.createUpload({ name: 'Ops cases', cases: '{"case_id":"C1"}\n', approved: true });
    expect(set.id).toBe('up-1');
    expect(calls[1].init.method).toBe('POST');
    expect(JSON.parse(calls[1].init.body as string)).toEqual({ name: 'Ops cases', cases: '{"case_id":"C1"}\n', approved: true });
  });

  it('explains a missing lexicon in plain language', () => {
    expect(describeError(new ApiError(400, 'lexicon_required', 'lexicon_id is required'))).toMatch(/Choose a lexicon first/);
    expect(describeError(new ApiError(404, 'lexicon_not_found', 'unknown lexicon x'))).toMatch(/no longer on the service/);
  });

  it('turns the error shape into an ApiError with code and message', async () => {
    const { fn } = fetchStub(() => ok({ error: { code: 'not_approved', message: 'Case set data has not been approved' } }, 403));
    const api = createApi({ base: '', token: '' }, fn);
    const err = await api.createJob({ mode: 'audit', client: { kind: 'sim' }, case_set: 'data', efforts: ['low'], runs: 1 }).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    const e = err as ApiError;
    expect(e.status).toBe(403);
    expect(e.code).toBe('not_approved');
    expect(e.message).toBe('Case set data has not been approved');
    expect(describeError(e)).toBe('Case set data has not been approved');
  });

  it('falls back to the status for non-JSON errors and describes network failures', async () => {
    const e = await errorFromResponse(new Response('<html>gateway</html>', { status: 502, statusText: 'Bad Gateway' }));
    expect(e.code).toBe('http_502');
    expect(e.message).toBe('<html>gateway</html>');
    const empty = await errorFromResponse(new Response(null, { status: 500, statusText: 'Internal Server Error' }));
    expect(empty.message).toBe('500 Internal Server Error');
    expect(describeError(new TypeError('Failed to fetch'))).toMatch(/Could not reach the service/);
  });
});

describe('operator keys and limits', () => {
  const base: Health = { version: '0.3.0', lexicon_version: null, modes: ['analyse', 'audit'], clients: ['sim', 'ollama', 'anthropic'], anonymous: 'analyse', workspace: 'public', domain: null, sections: [] };

  it('maps the limit error codes to plain language and leaves other codes alone', () => {
    expect(describeError(new ApiError(400, 'key_required', 'client.api_key is required'))).toMatch(/needs your own API key/);
    expect(describeError(new ApiError(413, 'job_too_large', 'Job needs 900 calls'))).toMatch(/fewer efforts, fewer runs/);
    expect(describeError(new ApiError(429, 'budget_exhausted', 'Daily budget exceeded'))).toMatch(/daily budget.*used up/i);
    expect(describeError(new ApiError(403, 'not_approved', 'Case set data has not been approved'))).toBe('Case set data has not been approved');
  });

  it('defaults the client kind to the first operator key, else sim', () => {
    expect(defaultClientKind(base)).toBe('sim');
    expect(defaultClientKind({ ...base, operator_keys: ['anthropic'] })).toBe('anthropic');
    expect(defaultClientKind({ ...base, operator_keys: ['openai'] })).toBe('sim');
    expect(defaultClientKind({ ...base, clients: ['ollama'] })).toBe('ollama');
  });

  it('computes the remaining daily budget, never negative, and null without limits', () => {
    expect(budgetRemaining(base)).toBeNull();
    expect(budgetRemaining({ ...base, limits: { max_calls_per_job: 400, max_calls_per_day: 2000, calls_used_today: 350, operator_keys: ['anthropic'] } })).toBe(1650);
    expect(budgetRemaining({ ...base, limits: { max_calls_per_job: 400, max_calls_per_day: 2000, calls_used_today: 2500, operator_keys: ['anthropic'] } })).toBe(0);
  });
});

describe('api settings', () => {
  it('round-trips through storage, normalising the base and tolerating junk', () => {
    const mem = new Map<string, string>();
    const storage: StorageLike = { getItem: (k) => mem.get(k) ?? null, setItem: (k, v) => { mem.set(k, v); } };
    expect(loadApiSettings(storage)).toEqual({ base: '', token: '' });
    saveApiSettings({ base: ' http://x/ ', token: 'tok' }, storage);
    expect(loadApiSettings(storage)).toEqual({ base: 'http://x', token: 'tok' });
    mem.set('traceaudit:api', '{not json');
    expect(loadApiSettings(storage)).toEqual({ base: '', token: '' });
    expect(normaliseBase('https://a.b//')).toBe('https://a.b');
  });
});
