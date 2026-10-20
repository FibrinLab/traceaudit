#!/usr/bin/env node
// Mock of `traceaudit serve` (specs/17-service.md §3) for developing the viewer's Analyse tab.
// Node only, no dependencies. Serves canned responses built from the packaged demo bundle.
//
//   npm run mock                      # http://127.0.0.1:8787
//   MOCK_PORT=9000 npm run mock
//   MOCK_TOKEN=secret npm run mock    # every request must carry `Authorization: Bearer secret`
//   MOCK_MAX_CALLS_PER_JOB=50 npm run mock   # exercise job_too_large; MOCK_CALLS_USED=1990 for budget_exhausted
//
// `/api/health` reports `operator_keys: ["anthropic"]` and `limits`, so the Audit form hides the key field for
// anthropic and shows the budget; jobs on the operator key count against the daily budget for the mock's lifetime.
// `/api/lexicons` lists the built-in haematology lexicon plus uploads (POST `{lexicon: <json text>, name?}`), kept in
// memory; `/api/analyse` with an uploaded `lexicon_id` grades the text with a small lexical grader so any domain works.
//
// Jobs advance one status per GET /api/jobs/:id poll (queued → running → scoring → exporting → done),
// so the viewer's polling can be watched end to end in a few seconds. `/api/jobs/:id/bundle/*` serves
// the demo bundle, and `/api/jobs/:id/files/*` serves small canned downloads. When `dist/` exists it is
// served at `/`, so `?bundle=/api/jobs/<id>/bundle/` works same-origin like the real service.

import { createServer } from 'node:http';
import { readFile, stat } from 'node:fs/promises';
import { createReadStream, existsSync } from 'node:fs';
import { dirname, extname, join, normalize, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { randomBytes } from 'node:crypto';

const here = dirname(fileURLToPath(import.meta.url));
const DEMO = resolve(here, '../public/demo');
const DIST = resolve(here, '../dist');
const PORT = Number(process.env.MOCK_PORT ?? 8787);
const TOKEN = process.env.MOCK_TOKEN ?? null;
const VERSION = '0.2.0-mock';

const index = JSON.parse(await readFile(join(DEMO, 'index.json'), 'utf8'));
const cll = JSON.parse(await readFile(join(DEMO, 'cases/CLL-001.json'), 'utf8'));
const exampleTrace = cll.traces.find((t) => t.variant === 'base' && t.effort === 'high' && t.run === 0) ?? cll.traces[0];

// Lexicons: the built-in haematology one (from the demo bundle) plus uploads, kept in memory for the mock's lifetime.
const DEFAULT_SECTIONS = [
  { id: 'clinical', title: 'Clinical summary' }, { id: 'morphology', title: 'Morphology' }, { id: 'flow_cytometry', title: 'Flow cytometry' },
  { id: 'cytogenetics', title: 'Cytogenetics' }, { id: 'molecular', title: 'Molecular' },
];
const DEFAULT_LEXICON = { id: 'default', name: 'haematology', domain: 'haematology', version: index.lexicon.version, sections: DEFAULT_SECTIONS,
  entities: index.lexicon.entities, findings: index.lexicon.findings, source: 'built-in' };
/** id → full lexicon record (meta fields + entities + findings) */
const lexicons = new Map([['default', DEFAULT_LEXICON]]);
function lexiconMeta(l) {
  return { id: l.id, name: l.name, domain: l.domain, version: l.version, sections: l.sections, n_findings: l.findings.length, n_entities: l.entities.filter((e) => e.in_scope !== false).length, source: l.source };
}
function uploadLexicon(body) {
  const text = typeof body.lexicon === 'string' ? body.lexicon : JSON.stringify(body.lexicon ?? null);
  let data;
  try { data = JSON.parse(text); } catch { return [400, { error: { code: 'bad_lexicon', message: 'lexicon rejected: not valid JSON' } }]; }
  const missing = ['version', 'domain', 'sections', 'entities', 'findings'].filter((k) => !(data && typeof data === 'object' && k in data));
  if (missing.length) return [400, { error: { code: 'bad_lexicon', message: `lexicon rejected: missing ${missing.join(', ')}` } }];
  if (!Array.isArray(data.sections) || !data.sections.length || !Array.isArray(data.entities) || !Array.isArray(data.findings)) return [400, { error: { code: 'bad_lexicon', message: 'lexicon rejected: sections, entities and findings must be non-empty arrays' } }];
  const id = 'lex-' + randomBytes(3).toString('hex');
  const rec = { id, name: body.name || data.domain, domain: String(data.domain), version: String(data.version), sections: data.sections.map((s) => ({ id: String(s.id), title: String(s.title ?? s.id) })),
    entities: data.entities, findings: data.findings, source: 'upload' };
  lexicons.set(id, rec);
  return [201, lexiconMeta(rec)];
}
function lexiconDisplay(l) {
  return { version: l.version, domain: l.domain, sections: l.sections,
    entities: l.entities.map((e) => ({ id: e.id, display: e.display, in_scope: e.in_scope !== false, parent: e.parent ?? null })),
    findings: l.findings.map((f) => ({ id: f.id, display: f.display, kind: f.kind })) };
}

const CASE_SETS = [
  { id: 'sample', name: 'Packaged sample (6 synthetic cases)', n_cases: 6, n_perturbations: 30, approved: true, source: 'packaged' },
  { id: 'data', name: 'Local data/ set (awaiting review)', n_cases: 40, n_perturbations: 180, approved: false, source: 'data' },
];

const MIME = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8', '.json': 'application/json; charset=utf-8', '.svg': 'image/svg+xml', '.woff2': 'font/woff2', '.woff': 'font/woff', '.png': 'image/png', '.md': 'text/markdown; charset=utf-8', '.jsonl': 'application/x-ndjson; charset=utf-8', '.csv': 'text/csv; charset=utf-8' };

/** job_id → { job, polls } */
const jobs = new Map();
const STATUS_SEQUENCE = ['queued', 'running', 'running', 'running', 'scoring', 'exporting', 'done'];

function cors(res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type, Authorization');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, DELETE, OPTIONS');
}
function sendJson(res, code, body) {
  cors(res);
  const data = Buffer.from(JSON.stringify(body, null, 1));
  res.writeHead(code, { 'Content-Type': 'application/json; charset=utf-8', 'Content-Length': data.length });
  res.end(data);
}
function sendError(res, code, errCode, message) { sendJson(res, code, { error: { code: errCode, message } }); }
async function sendFile(res, path, download = null) {
  try {
    const s = await stat(path);
    if (!s.isFile()) throw new Error('not a file');
  } catch {
    return sendError(res, 404, 'not_found', `No such file: ${path.slice(path.lastIndexOf('/') + 1)}`);
  }
  cors(res);
  const headers = { 'Content-Type': MIME[extname(path)] ?? 'application/octet-stream', 'Cache-Control': 'no-cache' };
  if (download) headers['Content-Disposition'] = `attachment; filename="${download}"`;
  res.writeHead(200, headers);
  createReadStream(path).pipe(res);
}
function sendText(res, text, type, download) {
  cors(res);
  const data = Buffer.from(text);
  res.writeHead(200, { 'Content-Type': type, 'Content-Length': data.length, 'Content-Disposition': `attachment; filename="${download}"` });
  res.end(data);
}
function readBody(req) {
  return new Promise((resolveBody, reject) => {
    const chunks = [];
    req.on('data', (c) => chunks.push(c));
    req.on('end', () => resolveBody(Buffer.concat(chunks).toString('utf8')));
    req.on('error', reject);
  });
}
function safeJoin(root, rel) {
  const p = normalize(join(root, rel));
  return p.startsWith(root) ? p : null;
}

// ---- handlers ------------------------------------------------------------------------------------

// Operator keys: client kinds the site runs on its own key, with a per-job cap and a daily budget (spec 17 §4).
const OPERATOR_KEYS = ['anthropic'];
const LIMITS = { max_calls_per_job: Number(process.env.MOCK_MAX_CALLS_PER_JOB ?? 400), max_calls_per_day: Number(process.env.MOCK_MAX_CALLS_PER_DAY ?? 2000), calls_used_today: Number(process.env.MOCK_CALLS_USED ?? 350) };

function health() {
  return {
    version: VERSION, lexicon_version: index.lexicon.version, modes: ['analyse', 'audit'], clients: ['sim', 'ollama', 'openai', 'anthropic'],
    anonymous: TOKEN ? 'none' : 'analyse', workspace: 'public',
    operator_keys: OPERATOR_KEYS,
    limits: { ...LIMITS, operator_keys: OPERATOR_KEYS },
    domain: DEFAULT_LEXICON.domain,
    sections: DEFAULT_SECTIONS,
  };
}

function lexicon(id) {
  const l = lexicons.get(id || 'default');
  return l ? [200, lexiconDisplay(l)] : [404, { error: { code: 'lexicon_not_found', message: `unknown lexicon ${id}` } }];
}

const cap = (s) => s.replace(/[_-]+/g, ' ').replace(/^\w/, (c) => c.toUpperCase());

/** A small lexical grader for uploaded lexicons: one claim per sentence, findings matched by alias, graded against the documents. */
function genericAnalyse(body, lx, documents, sections, oracle) {
  const docLower = Object.fromEntries(Object.entries(documents).map(([k, v]) => [k, (v || '').toLowerCase()]));
  const aliasesOf = (f) => [f.display, ...(f.aliases ?? [])].filter(Boolean).map((a) => a.toLowerCase());
  const locate = (f) => {
    for (const [k, v] of Object.entries(docLower)) for (const a of aliasesOf(f)) { const i = v.indexOf(a); if (i >= 0) return { report: k, start: i, end: i + a.length, surface: documents[k].slice(i, i + a.length) }; }
    return null;
  };
  const negated = (f, text) => (f.neg_phrases ?? []).some((p) => text.includes(p.toLowerCase())) || new RegExp(`\\b(no|not|normal|absent|negative)\\b[^.]{0,40}(${aliasesOf(f).map((a) => a.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|')})`, 'i').test(text);
  const truth = {}; const finding_spans = {};
  for (const f of lx.findings) {
    const loc = locate(f);
    if (!loc) continue;
    const pol = negated(f, docLower[loc.report]) ? 'neg' : 'pos';
    truth[f.id] = pol; finding_spans[f.id] = [{ ...loc, polarity: pol }];
  }
  if (oracle === 'truth') Object.assign(truth, body.truth);
  const reasoning = body.reasoning; const claims = []; let id = 0;
  const re = /[^.!?\n]+[.!?]?/g; let m;
  while ((m = re.exec(reasoning))) {
    const lead = m[0].length - m[0].trimStart().length; const text = m[0].trim(); if (!text) continue;
    const start = m.index + lead, end = start + text.length, lower = text.toLowerCase();
    const hits = lx.findings.filter((f) => aliasesOf(f).some((a) => lower.includes(a)));
    const inference = /\b(therefore|so|suggests?|likely|consistent with|points to|maybe|probably|conclude|root cause)\b/i.test(text);
    const type = hits.length ? 'factual' : inference ? 'inferential' : 'other';
    const evidence = []; const assertions = [];
    for (const f of hits) {
      const claimed = negated(f, lower) ? 'neg' : 'pos';
      const span = finding_spans[f.id]?.[0] ?? null;
      evidence.push({ finding_id: f.id, claimed, truth: truth[f.id] ?? null, report: span?.report ?? null, span: span ? [span.start, span.end] : null });
      const a = aliasesOf(f).find((x) => lower.includes(x)); const ai = lower.indexOf(a);
      assertions.push({ finding_id: f.id, polarity: claimed, start: start + ai, end: start + ai + a.length, surface: text.slice(ai, ai + a.length) });
    }
    const label = type !== 'factual' ? null : evidence.some((e) => e.truth !== null && e.truth !== e.claimed) ? 'contradicted' : evidence.some((e) => e.truth === null) ? 'unsupported' : 'supported';
    const entities = lx.entities.filter((e) => [e.display, ...(e.aliases ?? [])].some((a) => a && lower.includes(a.toLowerCase()))).map((e) => e.id);
    claims.push({ trace_key: 'ANL-001|base|medium|0', claim_id: id++, paragraph_id: 0, start, end, text, type, flags: [], assertions, label, evidence, knowledge_check: null, entities });
  }
  const ansLower = (body.answer || '').toLowerCase();
  const ent = lx.entities.find((e) => [e.display, ...(e.aliases ?? [])].some((a) => a && ansLower.includes(a.toLowerCase()))) ?? null;
  const factual = claims.filter((c) => c.type === 'factual');
  const n = (lab) => factual.filter((c) => c.label === lab).length;
  const grounding = {
    trace_key: 'ANL-001|base|medium|0', case_id: 'ANL-001', variant: 'base', effort: 'medium', run: 0,
    n_claims: claims.length, n_factual: factual.length, n_knowledge: 0, n_inferential: claims.filter((c) => c.type === 'inferential').length, n_other: claims.filter((c) => c.type === 'other').length,
    n_supported: n('supported'), n_contradicted: n('contradicted'), n_unsupported: n('unsupported'), n_ambiguous: 0,
    grounding_rate: factual.length ? n('supported') / factual.length : null,
    contradicted_findings: [...new Set(factual.filter((c) => c.label === 'contradicted').flatMap((c) => c.evidence.map((e) => e.finding_id)))],
    unsupported_findings: [...new Set(factual.filter((c) => c.label === 'unsupported').flatMap((c) => c.evidence.map((e) => e.finding_id)))],
    answer_entity: ent?.id ?? null, answer_entity_raw: ent?.display ?? null, answer_subtype: null, answer_hedged: /\b(maybe|possibly|might|unsure)\b/i.test(body.answer || ''),
    answer_correct: body.entity && ent ? ent.id === body.entity : null, trace_conclusion_entity: ent?.id ?? null, trace_answer_agree: null,
    knowledge_consistent: 0, knowledge_inconsistent: 0, knowledge_abstain: 0, error: null,
  };
  return { claims, grounding, truth, finding_spans, parsed_answer: { entity: ent?.id ?? null, entity_raw: ent?.display ?? null, subtype: null, hedged: grounding.answer_hedged, confidence: (/Confidence:\s*(\w+)/i.exec(body.answer || '') ?? [])[1]?.toLowerCase() ?? null } };
}

function analyse(body) {
  const lx = lexicons.get(body.lexicon_id || 'default');
  if (!lx) return [404, { error: { code: 'lexicon_not_found', message: `unknown lexicon ${body.lexicon_id}` } }];
  // General form `documents` (any section ids) or the haematology shorthand `reports`.
  const general = body.documents && typeof body.documents === 'object' && Object.keys(body.documents).length > 0;
  const documents = general ? body.documents : (body.reports ?? {});
  const known = Object.fromEntries(lx.sections.map((sec) => [sec.id, sec.title]));
  const sections = general
    ? Object.keys(documents).map((k) => ({ id: k, title: body.titles?.[k] || known[k] || cap(k) }))
    : lx.sections;
  if (Object.keys(documents).length > 20) return [400, { error: { code: 'bad_request', message: 'at most 20 documents' } }];
  for (const [k, v] of Object.entries(documents)) {
    if (typeof v !== 'string') return [400, { error: { code: 'bad_request', message: `document ${k} must be a string` } }];
    if (v.length > 50_000) return [400, { error: { code: 'too_large', message: `document ${k} exceeds 50 KB` } }];
  }
  if (!Object.values(documents).some((v) => v && v.trim())) return [400, { error: { code: 'bad_request', message: 'documents must contain at least one of ' + sections.map((sec) => sec.id).join(', ') } }];
  if (typeof body.reasoning !== 'string' || !body.reasoning.trim()) return [400, { error: { code: 'bad_request', message: 'reasoning is required: paste the model\'s reasoning text' } }];
  if (body.reasoning.length > 200_000) return [400, { error: { code: 'too_large', message: 'reasoning exceeds 200 KB' } }];
  if (typeof body.answer !== 'string' || !body.answer.trim()) return [400, { error: { code: 'bad_request', message: 'answer is required: paste the model\'s final answer' } }];
  const oracle = body.truth && typeof body.truth === 'object' && Object.keys(body.truth).length ? 'truth' : 'extracted';
  const lexiconOut = { id: lx.id, domain: lx.domain, version: lx.version, entities: lx.entities.map((e) => ({ id: e.id, display: e.display })), findings: lx.findings.map((f) => ({ id: f.id, display: f.display, kind: f.kind })) };
  if (lx.id !== 'default') {
    // Uploaded lexicon: grade the submitted text for real (lexically), so any domain gets a sensible result.
    const r = genericAnalyse(body, lx, documents, sections, oracle);
    const entity = body.entity || r.grounding.answer_entity || 'OTHER';
    return [200, {
      case: { case_id: 'ANL-001', entity, subtype: null, flags: { discordant: false, incomplete: false, atypical_features: [], missing_modalities: [] }, reports: documents, truth: r.truth, finding_spans: r.finding_spans, sections },
      lexicon: lexiconOut, claims: r.claims, grounding: r.grounding, map: null, parsed_answer: r.parsed_answer, oracle, warnings: [], lexicon_version: lx.version, domain: lx.domain,
    }];
  }
  const g = exampleTrace.grounding;
  const parsed_answer = {
    entity: g?.answer_entity ?? null,
    entity_raw: g?.answer_entity_raw ?? null,
    subtype: g?.answer_subtype ?? null,
    hedged: g?.answer_hedged ?? false,
    confidence: (/Confidence:\s*(\w+)/i.exec(body.answer) ?? [])[1]?.toLowerCase() ?? null,
  };
  // Canned: the claims, grounding and map of one demo trace. Offsets match the example reasoning text; the
  // documents and sections echo what was submitted so the section headings follow the request.
  const reports = general ? documents : { ...cll.case.reports, ...documents };
  return [200, {
    case: { case_id: body.case_id ?? cll.case.case_id, entity: body.entity ?? cll.case.entity, reports, truth: oracle === 'truth' ? body.truth : cll.case.truth, finding_spans: cll.case.finding_spans, sections },
    lexicon: lexiconOut,
    claims: exampleTrace.claims,
    grounding: exampleTrace.grounding,
    map: exampleTrace.map,
    parsed_answer,
    oracle,
    warnings: [],
    lexicon_version: lx.version,
    domain: lx.domain,
  }];
}

function jobPublic(entry) {
  const { job } = entry;
  const { api_key: _k, ...client } = job.config.client;
  return { ...job, config: { ...job.config, client } };
}

function createJob(body) {
  if (body.mode !== 'audit') return [400, { error: { code: 'bad_request', message: 'mode must be "audit"' } }];
  const set = CASE_SETS.find((s) => s.id === body.case_set);
  if (!set) return [404, { error: { code: 'not_found', message: `Unknown case set ${body.case_set}` } }];
  if (!set.approved) return [403, { error: { code: 'not_approved', message: `Case set ${set.name} has not been approved for audit runs` } }];
  const efforts = Array.isArray(body.efforts) && body.efforts.length ? body.efforts : ['medium'];
  const runs = Number(body.runs) || 1;
  if (runs < 1 || runs > 5) return [400, { error: { code: 'bad_request', message: 'runs must be between 1 and 5' } }];
  const client = body.client ?? {};
  if (!client.kind) return [400, { error: { code: 'bad_request', message: 'client.kind is required' } }];
  if (!health().clients.includes(client.kind)) return [403, { error: { code: 'client_not_allowed', message: `Client kind ${client.kind} is not allowed on this server` } }];
  if (client.kind !== 'sim' && !client.model) return [400, { error: { code: 'bad_request', message: 'client.model is required' } }];
  const total = (set.n_cases + set.n_perturbations) * efforts.length * runs;
  const onOperatorKey = OPERATOR_KEYS.includes(client.kind) && !client.api_key;
  if (client.kind !== 'sim' && client.kind !== 'ollama' && !client.api_key && !OPERATOR_KEYS.includes(client.kind)) {
    return [400, { error: { code: 'key_required', message: `Client kind ${client.kind} needs an API key on this server` } }];
  }
  if (onOperatorKey) {
    if (total > LIMITS.max_calls_per_job) return [413, { error: { code: 'job_too_large', message: `Job needs ${total} calls; the limit per job is ${LIMITS.max_calls_per_job}` } }];
    if (LIMITS.calls_used_today + total > LIMITS.max_calls_per_day) return [429, { error: { code: 'budget_exhausted', message: `Daily budget of ${LIMITS.max_calls_per_day} calls would be exceeded` } }];
    LIMITS.calls_used_today += total;
  }
  const job_id = 'job-' + randomBytes(4).toString('hex');
  const now = new Date().toISOString();
  const job = {
    job_id, status: 'queued', created: now, started: null, finished: null,
    progress: { done: 0, total, ok: 0, errors: 0, eta_s: null },
    config: { mode: 'audit', client: { kind: client.kind, endpoint: client.endpoint ?? null, model: client.model ?? 'simulated', api_key: client.api_key ?? null }, case_set: set.id, efforts, runs, notes: body.notes ?? '' },
    error: null, headline: null,
  };
  jobs.set(job_id, { job, polls: 0 });
  return [202, { job_id }];
}

/** Advance a job one step per poll so the viewer can watch the whole lifecycle. */
function advance(entry) {
  const { job } = entry;
  if (['done', 'failed', 'cancelled', 'interrupted'].includes(job.status)) return;
  entry.polls += 1;
  const next = STATUS_SEQUENCE[Math.min(entry.polls, STATUS_SEQUENCE.length - 1)];
  if (job.status === 'queued' && next !== 'queued') job.started = new Date().toISOString();
  job.status = next;
  const runningSteps = STATUS_SEQUENCE.filter((s) => s === 'running').length;
  const runningIdx = Math.max(0, entry.polls - 1);
  if (next === 'running') {
    const frac = Math.min(1, (runningIdx + 1) / (runningSteps + 1));
    job.progress.done = Math.round(job.progress.total * frac);
    job.progress.errors = frac > 0.5 ? 1 : 0;
    job.progress.ok = job.progress.done - job.progress.errors;
    job.progress.eta_s = Math.round((job.progress.total - job.progress.done) * 0.4);
  } else if (next === 'scoring' || next === 'exporting') {
    job.progress.done = job.progress.total; job.progress.ok = job.progress.total - job.progress.errors; job.progress.eta_s = next === 'scoring' ? 6 : 2;
  } else if (next === 'done') {
    job.progress.done = job.progress.total; job.progress.ok = job.progress.total - job.progress.errors; job.progress.eta_s = 0;
    job.finished = new Date().toISOString();
    const gr = index.summary.grounding?.pooled_rate?.point;
    job.headline = `Grounding ${gr != null ? Math.round(gr * 100) + '%' : 'n/a'} across ${job.progress.total} traces, ${job.progress.errors} error${job.progress.errors === 1 ? '' : 's'}`;
  }
}

function cannedFile(name) {
  switch (name) {
    case 'summary.json': return [JSON.stringify(index.summary, null, 1), MIME['.json']];
    case 'manifest.json': return [JSON.stringify(index.run.manifest, null, 1), MIME['.json']];
    case 'report.md': return [`# traceaudit report (mock)\n\nRun ${index.run.run_id}\n\n- traces: ${index.summary.counts.traces}\n- pooled grounding rate: ${index.summary.grounding?.pooled_rate?.point ?? 'n/a'}\n`, MIME['.md']];
    case 'traces.jsonl': return [cll.traces.slice(0, 5).map((t) => JSON.stringify({ trace_key: t.trace_key, effort: t.effort, run: t.run, answer: t.answer })).join('\n') + '\n', MIME['.jsonl']];
    case 'long.csv': return ['trace_key,effort,run,grounding_rate\n' + cll.traces.slice(0, 5).map((t) => `${t.trace_key},${t.effort},${t.run},${t.grounding?.grounding_rate ?? ''}`).join('\n') + '\n', MIME['.csv']];
    default: return null;
  }
}

// ---- server ------------------------------------------------------------------------------------

const server = createServer(async (req, res) => {
  const url = new URL(req.url ?? '/', `http://${req.headers.host ?? 'localhost'}`);
  const path = url.pathname;
  if (req.method === 'OPTIONS') { cors(res); res.writeHead(204); return res.end(); }

  if (path.startsWith('/api/')) {
    if (TOKEN) {
      const auth = req.headers.authorization ?? '';
      if (auth !== `Bearer ${TOKEN}`) return sendError(res, 401, 'unauthorised', 'A valid bearer token is required for this server');
    }
    try {
      if (req.method === 'GET' && path === '/api/health') return sendJson(res, 200, health());
      if (req.method === 'GET' && path === '/api/lexicon') { const [code, out] = lexicon(url.searchParams.get('id')); return sendJson(res, code, out); }
      if (req.method === 'GET' && path === '/api/lexicons') return sendJson(res, 200, [...lexicons.values()].map(lexiconMeta));
      if (req.method === 'POST' && path === '/api/lexicons') {
        let body;
        try { body = JSON.parse(await readBody(req) || '{}'); } catch { return sendError(res, 400, 'bad_json', 'Request body is not valid JSON'); }
        const [code, out] = uploadLexicon(body);
        return sendJson(res, code, out);
      }
      if (req.method === 'GET' && path === '/api/case-sets') return sendJson(res, 200, CASE_SETS);
      if (req.method === 'POST' && path === '/api/analyse') {
        let body;
        try { body = JSON.parse(await readBody(req) || '{}'); } catch { return sendError(res, 400, 'bad_json', 'Request body is not valid JSON'); }
        const [code, out] = analyse(body);
        return sendJson(res, code, out);
      }
      if (req.method === 'POST' && path === '/api/uploads') return sendError(res, 501, 'not_implemented', 'Uploads are not part of this mock');
      if (req.method === 'POST' && path === '/api/jobs') {
        let body;
        try { body = JSON.parse(await readBody(req) || '{}'); } catch { return sendError(res, 400, 'bad_json', 'Request body is not valid JSON'); }
        const [code, out] = createJob(body);
        return sendJson(res, code, out);
      }
      if (req.method === 'GET' && path === '/api/jobs') {
        const list = [...jobs.values()].sort((a, b) => b.job.created.localeCompare(a.job.created)).map(({ job }) => ({ job_id: job.job_id, status: job.status, created: job.created, progress: job.progress, summary_headline: job.headline ?? undefined }));
        return sendJson(res, 200, list);
      }
      const m = /^\/api\/jobs\/([^/]+)(?:\/(.*))?$/.exec(path);
      if (m) {
        const entry = jobs.get(m[1]);
        if (!entry) return sendError(res, 404, 'not_found', `No job ${m[1]} in this workspace`);
        const rest = m[2] ?? '';
        if (req.method === 'GET' && rest === '') { advance(entry); return sendJson(res, 200, jobPublic(entry)); }
        if (req.method === 'DELETE' && rest === '') {
          const { job } = entry;
          if (!['queued', 'running'].includes(job.status)) return sendError(res, 409, 'conflict', `Job ${job.job_id} is ${job.status} and cannot be cancelled`);
          job.status = 'cancelled'; job.finished = new Date().toISOString(); job.progress.eta_s = null;
          return sendJson(res, 200, jobPublic(entry));
        }
        if (req.method === 'POST' && rest === 'resume') { entry.job.status = 'queued'; entry.polls = 0; return sendJson(res, 202, { job_id: entry.job.job_id }); }
        if (req.method === 'GET' && rest.startsWith('bundle/')) {
          if (entry.job.status !== 'done') return sendError(res, 409, 'not_ready', `Job ${entry.job.job_id} is ${entry.job.status}; the bundle is written when it is done`);
          const rel = rest.slice('bundle/'.length) || 'index.json';
          const p = safeJoin(DEMO, rel);
          return p ? sendFile(res, p) : sendError(res, 400, 'bad_path', 'Invalid bundle path');
        }
        if (req.method === 'GET' && rest.startsWith('files/')) {
          if (entry.job.status !== 'done') return sendError(res, 409, 'not_ready', `Job ${entry.job.job_id} is ${entry.job.status}; files are written when it is done`);
          const name = rest.slice('files/'.length);
          const f = cannedFile(name);
          return f ? sendText(res, f[0], f[1], name) : sendError(res, 404, 'not_found', `No file ${name}`);
        }
      }
      return sendError(res, 404, 'not_found', `No endpoint ${req.method} ${path}`);
    } catch (e) {
      return sendError(res, 500, 'internal', e instanceof Error ? e.message : String(e));
    }
  }

  // Static: the built viewer when present (so ?bundle=/api/jobs/<id>/bundle/ is same-origin).
  if (req.method === 'GET' && existsSync(DIST)) {
    const rel = path === '/' ? 'index.html' : decodeURIComponent(path.slice(1));
    const p = safeJoin(DIST, rel);
    if (p && existsSync(p)) return sendFile(res, p);
  }
  if (req.method === 'GET' && path.startsWith('/demo/')) {
    const p = safeJoin(DEMO, decodeURIComponent(path.slice('/demo/'.length)));
    if (p) return sendFile(res, p);
  }
  sendError(res, 404, 'not_found', `Nothing at ${path} (build the viewer with npm run build to serve it here)`);
});

server.listen(PORT, '127.0.0.1', () => {
  console.log(`traceaudit mock service on http://127.0.0.1:${PORT}  (token: ${TOKEN ? 'required' : 'none'}; static: ${existsSync(DIST) ? 'dist/' : 'none'})`);
});
