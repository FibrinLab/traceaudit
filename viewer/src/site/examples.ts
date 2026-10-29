// Example payloads the landing page and the manual send to the live API. The incident-triage example ships with the
// service (`examples/` in the repository); the ledger example is a tiny synthetic case so the shapes are visible.

export const INCIDENT_LEXICON_ID = 'example:incident-triage';

export const INCIDENT_REQUEST = {
  lexicon_id: INCIDENT_LEXICON_ID,
  documents: {
    alerts: 'Error rate elevated since 14:02 (5xx spike). CPU normal. No traffic spike.',
    logs: 'Database latency normal. Disk usage normal. Stack traces show NullPointerException in checkout.',
    deploys: 'Release 2026.10.20-3 went out at 13:55 (recent deploy).',
  },
  reasoning:
    'Error rate elevated right after a recent deploy. CPU saturated though, so maybe capacity. Database latency normal. ' +
    'The timing points to the release. Disk usage is normal, so not disk. The stack traces are in checkout, which the release touched. ' +
    'A faulty deployment explains the error spike best; capacity is less likely given no traffic spike.',
  answer: 'Diagnosis: faulty deployment\nConfidence: high',
};

export const LEDGER_REQUEST = {
  case: {
    case_id: 'DOC-001',
    truth: 'K1',
    candidates: ['K1', 'K2'],
    facts: [
      { id: 'p_1', source: 'patient', section: 'panel', field: 'f1', value: 'Positive', evidence: 'f1 positive', candidate: null },
      { id: 'p_2', source: 'patient', section: 'panel', field: 'f2', value: 'Positive', evidence: 'f2 positive', candidate: null },
      { id: 'p_3', source: 'patient', section: 'panel', field: 'f3', value: 'Negative', evidence: 'f3 negative', candidate: null },
      { id: 'w_1', source: 'who', section: 'reference', field: 'K1 essential', value: 'f1 positive and f3 negative', evidence: 'K1: f1 positive, f3 negative', candidate: 'K1' },
      { id: 'w_2', source: 'who', section: 'reference', field: 'K2 essential', value: 'f3 positive', evidence: 'K2: f3 positive', candidate: 'K2' },
    ],
  },
  trace: {
    thinking: 'f1 positive (p_1). f3 negative (p_3), which argues against K2 (w_2). The pattern fits K1 (w_1).',
    report: {
      decision: 'K1',
      sections: [
        { title: 'Summary', segments: [{ text: 'Diagnosis: K1, on the basis of f1 positive and f3 negative.', citation_ids: ['p_1', 'p_3'] }] },
        { title: 'Panel', segments: [{ text: 'f2 negative.', citation_ids: ['p_2'] }] },
      ],
    },
  },
};

export const JOB_REQUEST = {
  mode: 'audit',
  client: { kind: 'sim', model: 'simulated' },
  case_set: 'sample',
  efforts: ['low', 'high'],
  runs: 2,
  rule: 'D1',
  notes: 'playground run on the simulated model',
};

export const LEXICON_UPLOAD_REQUEST = {
  name: 'my domain',
  lexicon: '{"version": "0.1.0", "domain": "my-domain", "sections": [...], "entities": [...], "findings": [...]}',
};

/** The origin requests go to: the configured API base, else the page's own origin (the site proxies `/api/*`). */
export function apiOrigin(base: string): string {
  if (base) return base.replace(/\/+$/, '');
  if (typeof window !== 'undefined' && window.location?.origin && window.location.origin !== 'null') return window.location.origin;
  return 'https://traceaudit.pages.dev';
}

/** A curl command equivalent to a request from the page, body passed through a quoted heredoc so nothing needs escaping. */
export function curlFor(method: string, url: string, body?: string, token?: string): string {
  const auth = token ? ` \\\n  -H 'authorization: Bearer <token>'` : '';
  if (!body) return `curl -s${method === 'GET' ? '' : ` -X ${method}`} '${url}'${auth}`;
  return `curl -s -X ${method} '${url}' \\\n  -H 'content-type: application/json'${auth} \\\n  --data-binary @- <<'JSON'\n${body}\nJSON`;
}

export function stringify(value: unknown): string { return JSON.stringify(value, null, 1); }
