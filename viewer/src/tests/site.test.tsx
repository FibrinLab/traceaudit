import { describe, expect, it, beforeEach, vi } from 'vitest';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { parseHash, hrefDocs } from '../lib/router';
import { curlFor, apiOrigin, INCIDENT_REQUEST, LEDGER_REQUEST, stringify } from '../site/examples';
import { ApiTry } from '../site/ApiTry';
import { AnalyseSummary } from '../site/Landing';
import { CHAPTERS, chapterBySlug } from '../site/docs/index';
import { resetHealthCache } from '../site/useHealth';
import { StoreProvider } from '../store';
import { App } from '../App';

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });
}

const HEALTH = { version: '0.2.0', modes: ['analyse', 'audit'], clients: ['anthropic', 'sim'], anonymous: 'all', workspace: 'public', operator_keys: ['anthropic'],
  limits: { max_calls_per_job: 200, max_calls_per_day: 2000, calls_used_today: 0, operator_keys: ['anthropic'] }, domain: null, sections: [] };

beforeEach(() => {
  resetHealthCache();
  window.location.hash = '';
  vi.restoreAllMocks();
});

describe('site routes', () => {
  it('parses the manual routes and keeps the others', () => {
    expect(parseHash('')).toEqual({ name: 'home' });
    expect(parseHash('#/docs')).toEqual({ name: 'docs', slug: 'overview', anchor: null });
    expect(parseHash('#/docs/api')).toEqual({ name: 'docs', slug: 'api', anchor: null });
    expect(parseHash('#/docs/api/analyse')).toEqual({ name: 'docs', slug: 'api', anchor: 'analyse' });
    expect(parseHash('#/analyse')).toEqual({ name: 'analyse', page: 'chooser' });
    expect(hrefDocs('ledger', 'checks')).toBe('#/docs/ledger/checks');
  });

  it('numbers the chapters consecutively and every section id is unique within its chapter', () => {
    CHAPTERS.forEach((c, i) => {
      expect(c.n).toBe(i + 1);
      const ids = c.sections.map((s) => s.id);
      expect(new Set(ids).size).toBe(ids.length);
    });
    expect(chapterBySlug('nope')).toBeNull();
  });
});

describe('examples and curl', () => {
  it('builds a curl with a quoted heredoc body and never a token value', () => {
    const c = curlFor('POST', 'https://x.test/api/analyse', '{"a": 1}', 'secret');
    expect(c).toContain("-X POST 'https://x.test/api/analyse'");
    expect(c).toContain("<<'JSON'\n{\"a\": 1}\nJSON");
    expect(c).toContain('Bearer <token>');
    expect(c).not.toContain('secret');
    expect(curlFor('GET', 'https://x.test/api/health')).toBe("curl -s 'https://x.test/api/health'");
  });
  it('uses the configured base, else the page origin', () => {
    expect(apiOrigin('https://api.test/')).toBe('https://api.test');
    expect(apiOrigin('')).toBe(window.location.origin);
  });
  it('ships well-formed example bodies', () => {
    expect(INCIDENT_REQUEST.lexicon_id).toBe('example:incident-triage');
    expect(Object.keys(INCIDENT_REQUEST.documents)).toEqual(['alerts', 'logs', 'deploys']);
    expect(LEDGER_REQUEST.trace.report.sections[1].segments[0].citation_ids).toEqual(['p_2']);
    expect(() => JSON.parse(stringify(LEDGER_REQUEST))).not.toThrow();
  });
});

describe('ApiTry', () => {
  it('sends the edited body with the JSON header and renders the response', async () => {
    const fetchImpl = vi.fn(async (_url: RequestInfo | URL, init?: RequestInit) => {
      expect(init?.method).toBe('POST');
      expect((init?.headers as Record<string, string>)['Content-Type']).toBe('application/json');
      expect(JSON.parse(String(init?.body))).toEqual({ hello: 'world' });
      return jsonResponse({ ok: true, echo: 1 });
    }) as unknown as typeof fetch;
    render(<StoreProvider><ApiTry method="POST" path="/api/analyse" body='{"hello": "world"}' fetchImpl={fetchImpl} /></StoreProvider>);
    fireEvent.click(screen.getByRole('button', { name: 'Send' }));
    await waitFor(() => expect(screen.getByText(/200/)).toBeTruthy());
    expect(fetchImpl).toHaveBeenCalledTimes(1);
    expect(String((fetchImpl as unknown as { mock: { calls: unknown[][] } }).mock.calls[0][0])).toMatch(/\/api\/analyse$/);
    expect(screen.getByText(/"echo": 1/)).toBeTruthy();
  });

  it('refuses a body that is not JSON before calling the service', async () => {
    const fetchImpl = vi.fn() as unknown as typeof fetch;
    render(<StoreProvider><ApiTry method="POST" path="/api/analyse" body='{not json' fetchImpl={fetchImpl} /></StoreProvider>);
    fireEvent.click(screen.getByRole('button', { name: 'Send' }));
    await waitFor(() => expect(screen.getByRole('alert').textContent).toMatch(/not valid JSON/));
    expect(fetchImpl).not.toHaveBeenCalled();
  });

  it('shows the curl equivalent on request', () => {
    render(<StoreProvider><ApiTry method="GET" path="/api/health" /></StoreProvider>);
    fireEvent.click(screen.getByRole('button', { name: 'curl' }));
    expect(screen.getByText(/curl -s '.*\/api\/health'/)).toBeTruthy();
  });

  it('renders an error status without a summary', async () => {
    const fetchImpl = vi.fn(async () => jsonResponse({ error: { code: 'bad_request', message: 'nope' } }, 400)) as unknown as typeof fetch;
    render(<StoreProvider><ApiTry method="POST" path="/api/ledger" body="{}" fetchImpl={fetchImpl} summary={() => <b>never</b>} /></StoreProvider>);
    fireEvent.click(screen.getByRole('button', { name: 'Send' }));
    await waitFor(() => expect(screen.getByText(/400/)).toBeTruthy());
    expect(screen.queryByText('never')).toBeNull();
    expect(screen.getByText(/bad_request/)).toBeTruthy();
  });
});

describe('AnalyseSummary', () => {
  it('reads metrics, grades and failed checks from a ledger result', () => {
    const data = {
      decision: 'BAD_DEPLOY', answer: { entity: 'BAD_DEPLOY', hedged: false },
      metrics: { grounding_rate: 0.75, facts: 6, cited_agree: 3, cited_disagree: 1, checks_failed: 2, checks_total: 24 },
      checks: [{ id: 'citations_agree', title: 'Cited facts are stated with their recorded value', status: 'FAIL', detail: '1 disagree' }, { id: 'thinking_present', title: 'Thinking returned', status: 'PASS' }],
      sections: [{ title: 'Answer', segments: [{ text: 'CPU saturated though.', citation_ids: ['p_2'], cited: [{ id: 'p_2', grade: 'disagree', field: 'cpu_saturated', value: 'neg' }] }, { text: 'Therefore.', citation_ids: [], cited: [] }] }],
    };
    render(<AnalyseSummary data={data} />);
    expect(screen.getByText('75%')).toBeTruthy();
    expect(screen.getByText('2/24')).toBeTruthy();
    expect(screen.getByText(/p_2 disagree/)).toBeTruthy();
    expect(screen.getByText('no factual claim')).toBeTruthy();
    expect(screen.getByText('citations_agree')).toBeTruthy();
    expect(screen.queryByText('thinking_present')).toBeNull();
  });
});

describe('App front page and manual', () => {
  it('renders the landing page at #/ with the live health line, not the viewer chrome', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async () => jsonResponse(HEALTH));
    render(<StoreProvider><App /></StoreProvider>);
    expect(screen.getByRole('heading', { level: 1, name: 'Does the reasoning hold up?' })).toBeTruthy();
    expect(screen.queryByText('Trace Viewer')).toBeNull();
    await waitFor(() => expect(screen.getByText(/service 0\.2\.0/)).toBeTruthy());
    expect(screen.getByLabelText('Live service status').textContent).toMatch(/GET \/api\/health\s+200\s+version 0\.2\.0/);
    const primary = screen.getAllByRole('link', { name: 'Open the viewer' }).find((a) => a.className.includes('primary'));
    expect(primary?.getAttribute('href')).toBe('#/analyse');
    expect(screen.getByRole('button', { name: 'Send to /api/analyse' })).toBeTruthy();
  });

  it('renders every chapter of the manual without throwing and marks the current one', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async () => jsonResponse(HEALTH));
    for (const c of CHAPTERS) {
      window.location.hash = hrefDocs(c.slug);
      const { unmount } = render(<StoreProvider><App /></StoreProvider>);
      expect(screen.getByRole('heading', { level: 1, name: c.title })).toBeTruthy();
      expect(screen.getByRole('link', { name: `${c.n} ${c.title}` }).getAttribute('aria-current')).toBe('page');
      unmount();
    }
  });

  it('says so for a chapter that does not exist', () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async () => jsonResponse(HEALTH));
    window.location.hash = '#/docs/nothing';
    render(<StoreProvider><App /></StoreProvider>);
    expect(screen.getByRole('heading', { level: 1, name: 'No such chapter' })).toBeTruthy();
  });

  it('still opens the viewer at #/analyse', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async () => jsonResponse(HEALTH));
    window.location.hash = '#/analyse';
    await act(async () => { render(<StoreProvider><App /></StoreProvider>); });
    expect(screen.getByText('Trace Viewer')).toBeTruthy();
  });
});
