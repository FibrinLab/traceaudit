#!/usr/bin/env node
// Mock of `traceaudit serve` (specs/17-service.md §3) for developing the viewer's Analyse tab.
// Node ≥ 22.18 (it imports the TypeScript test fixture directly), no dependencies. Nothing domain-specific is built in.
//
//   npm run mock                      # http://127.0.0.1:8787
//   MOCK_PORT=9000 npm run mock
//   MOCK_TOKEN=secret npm run mock    # every request must carry `Authorization: Bearer secret`
//   MOCK_MAX_CALLS_PER_JOB=50 npm run mock   # exercise job_too_large; MOCK_CALLS_USED=1990 for budget_exhausted
//
// Contract (same as the service):
//   GET  /api/health      no default lexicon: `domain: null`, `sections: []`, `lexicon_version: null`; plus
//                         `operator_keys: ["anthropic"]` and `limits`, so the Audit form hides the key field and shows the budget.
//   GET  /api/lexicons    the starter lexicons shipped as examples (`source: "example"`, e.g. `example:incident-triage`,
//                         read from public/examples/) then the workspace's uploads (`source: "upload"`, POST `{lexicon, name?}`).
//   GET  /api/lexicon?id= one lexicon's display data; 400 lexicon_required without an id, 404 lexicon_not_found otherwise.
//   POST /api/ledger      `{markdown}` or `{case, trace}` → the canned fact-ledger audit in mock/fixtures/ledger-result.json
//                         (produced by `traceaudit ledger audit tests/fixtures/synthetic_trace_SYN-003.md --json`).
//   POST /api/analyse     400 lexicon_required without a usable `lexicon_id`; the packaged example inputs get the real
//                         service's result (mock/fixtures/analyse-result.json, from `POST /api/analyse` on
//                         examples/incident-trace.json with the incident-triage lexicon); anything else is graded by a
//                         small lexical grader into the same shape: a fact-ledger result plus `documents` with fact spans.
//   GET  /api/case-sets   empty until POST /api/uploads `{name, cases: <jsonl>, approved}` adds one (kept in memory).
//   Jobs advance one status per GET /api/jobs/:id poll (queued → running → scoring → exporting → done); a finished job's
//   bundle (`/api/jobs/:id/bundle/*`) and files are generated from the synthetic incident-triage fixture, so the Cohort and
//   Cases tabs have something to show. When `dist/` exists it is served at `/`, so `?bundle=/api/jobs/<id>/bundle/` works
//   same-origin like the real service.

import { createServer } from 'node:http';
import { readFile, stat } from 'node:fs/promises';
import { createReadStream, existsSync } from 'node:fs';
import { dirname, extname, join, normalize, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { randomBytes } from 'node:crypto';
import { makeIncidentBundle } from '../src/tests/fixtures/incidentBundle.ts';

const here = dirname(fileURLToPath(import.meta.url));
const EXAMPLES = resolve(here, '../public/examples');
const DIST = resolve(here, '../dist');
const LEDGER_FIXTURE = resolve(here, 'fixtures/ledger-result.json');
const ANALYSE_FIXTURE = resolve(here, 'fixtures/analyse-result.json');
const PORT = Number(process.env.MOCK_PORT ?? 8787);
const TOKEN = process.env.MOCK_TOKEN ?? null;
const VERSION = '0.3.0-mock';

// ---- lexicons ------------------------------------------------------------------------------------

/** id → full lexicon record (meta fields + entities + findings). Examples first, uploads appended for the mock's lifetime. */
const lexicons = new Map();
async function loadExampleLexicons() {
  const data = JSON.parse(await readFile(join(EXAMPLES, 'lexicon-incident-triage.json'), 'utf8'));
  lexicons.set('example:incident-triage', lexiconRecord('example:incident-triage', data, cap(data.domain), 'example'));
}
function lexiconRecord(id, data, name, source) {
  return { id, name, domain: String(data.domain), version: String(data.version), sections: data.sections.map((s) => ({ id: String(s.id), title: String(s.title ?? s.id) })), entities: data.entities, findings: data.findings, source };
}
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
  const rec = lexiconRecord(id, data, body.name || data.domain, 'upload');
  lexicons.set(id, rec);
  return [201, lexiconMeta(rec)];
}
function lexiconDisplay(l) {
  return { version: l.version, domain: l.domain, sections: l.sections,
    entities: l.entities.map((e) => ({ id: e.id, display: e.display, in_scope: e.in_scope !== false, parent: e.parent ?? null })),
    findings: l.findings.map((f) => ({ id: f.id, display: f.display, kind: f.kind })) };
}
function lexicon(id) {
  if (!id) return [400, { error: { code: 'lexicon_required', message: 'id is required: the service has no default lexicon' } }];
  const l = lexicons.get(id);
  return l ? [200, lexiconDisplay(l)] : [404, { error: { code: 'lexicon_not_found', message: `unknown lexicon ${id}` } }];
}
const cap = (s) => s.replace(/[_-]+/g, ' ').replace(/^\w/, (c) => c.toUpperCase());

// ---- case sets (uploads) -------------------------------------------------------------------------

/** Empty until something is uploaded. */
const CASE_SETS = [];
function createUpload(body) {
  const name = typeof body.name === 'string' ? body.name.trim() : '';
  if (!name) return [400, { error: { code: 'bad_request', message: 'name is required' } }];
  if (typeof body.cases !== 'string' || !body.cases.trim()) return [400, { error: { code: 'bad_request', message: 'cases is required: JSONL text, one case or perturbation per line' } }];
  let n_cases = 0, n_perturbations = 0;
  const lines = body.cases.split(/\r?\n/).filter((l) => l.trim());
  for (const [i, line] of lines.entries()) {
    let row;
    try { row = JSON.parse(line); } catch { return [400, { error: { code: 'bad_request', message: `line ${i + 1} is not valid JSON` } }]; }
    if (!row || typeof row !== 'object' || typeof row.case_id !== 'string') return [400, { error: { code: 'bad_request', message: `line ${i + 1} has no case_id` } }];
    if (row.variant || row.edits || row.perturbation_id) n_perturbations++; else n_cases++;
  }
  if (!n_cases) return [400, { error: { code: 'bad_request', message: 'no cases: every line is a perturbation' } }];
  const set = { id: 'up-' + randomBytes(3).toString('hex'), name, n_cases, n_perturbations, approved: body.approved !== false, source: 'upload' };
  CASE_SETS.push(set);
  return [201, set];
}

const MIME = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8', '.json': 'application/json; charset=utf-8', '.svg': 'image/svg+xml', '.woff2': 'font/woff2', '.woff': 'font/woff', '.png': 'image/png', '.md': 'text/markdown; charset=utf-8', '.jsonl': 'application/x-ndjson; charset=utf-8', '.csv': 'text/csv; charset=utf-8' };

/** job_id → { job, polls, bundle } */
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
    version: VERSION, lexicon_version: null, modes: ['analyse', 'audit'], clients: ['sim', 'ollama', 'openai', 'anthropic'],
    anonymous: TOKEN ? 'none' : 'analyse', workspace: 'public',
    operator_keys: OPERATOR_KEYS,
    limits: { ...LIMITS, operator_keys: OPERATOR_KEYS },
    domain: null,
    sections: [],
  };
}

/** A small lexical grader into the fact-ledger shape: every finding stated in a document is a fact (alias found,
 *  polarity from the surrounding negation); every sentence of the reasoning that names a finding is a segment citing
 *  that finding's fact, graded agree/disagree by comparing polarities. */
function genericAnalyse(body, lx, documents, sections, oracle) {
  const docs = sections.map((sec) => ({ id: sec.id, title: sec.title, text: documents[sec.id] || '' }));
  const esc = (x) => x.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const aliasesOf = (f) => [f.display, ...(f.aliases ?? [])].filter(Boolean).map((a) => a.toLowerCase());
  const negated = (f, text) => (f.neg_phrases ?? []).some((p) => text.includes(p.toLowerCase())) || new RegExp(`\\b(no|not|normal|absent|negative)\\b[^.]{0,40}(${aliasesOf(f).map(esc).join('|')})`, 'i').test(text);
  const word = (pol) => (pol === 'neg' ? 'Negative' : 'Positive');
  const truth = oracle === 'truth' ? body.truth : {};
  // facts, in document order
  const facts = []; const spans = {};
  for (const d of docs) {
    const low = d.text.toLowerCase();
    const found = [];
    for (const f of lx.findings) {
      let hit = null;
      for (const a of aliasesOf(f)) { const i = low.indexOf(a); if (i >= 0 && (!hit || i < hit.start)) hit = { start: i, end: i + a.length, polarity: negated(f, low) ? 'neg' : 'pos' }; }
      for (const p of (f.neg_phrases ?? []).map((x) => x.toLowerCase())) { const i = low.indexOf(p); if (i >= 0 && (!hit || i < hit.start)) hit = { start: i, end: i + p.length, polarity: 'neg' }; }
      if (hit) found.push({ f, ...hit });
    }
    found.sort((a, b) => a.start - b.start);
    for (const h of found) {
      const id = `p_${facts.length + 1}`;
      const polarity = truth[h.f.id] ?? h.polarity;
      facts.push({ id, source: 'patient', section: d.id, field: h.f.id, value: word(polarity), evidence: d.text.slice(h.start, h.end), candidate: null, polarity, informative: true,
        referenced_in_thinking: false, cited_in_report: false, cited_in_rationale: false, ignored: false });
      spans[id] = { report: d.id, start: h.start, end: h.end };
    }
  }
  const byField = new Map();
  for (const f of facts) if (!byField.has(f.field)) byField.set(f.field, f);
  // segments: the reasoning's sentences that state a finding
  const reasoning = body.reasoning; const lowR = reasoning.toLowerCase();
  const segments = []; let agree = 0, disagree = 0, uncitedAssertions = 0, uncitedSegments = 0;
  const re = /[^.!?\n]+[.!?]?/g; let m; let nClaims = 0;
  while ((m = re.exec(reasoning))) {
    const text = m[0].trim(); if (!text) continue;
    nClaims++;
    const lower = text.toLowerCase();
    const hits = lx.findings.filter((f) => aliasesOf(f).some((a) => lower.includes(a)));
    if (!hits.length) continue;
    const cited = []; const uncited = []; const citation_ids = [];
    for (const f of hits) {
      const stated = negated(f, lower) ? 'neg' : 'pos';
      const fact = byField.get(f.id);
      if (!fact) { uncited.push({ field: f.id, stated, fact_id: null, value: null, grade: 'unknown_fact' }); uncitedAssertions++; continue; }
      const grade = fact.polarity === stated ? 'agree' : 'disagree';
      if (grade === 'agree') agree++; else disagree++;
      citation_ids.push(fact.id); fact.cited_in_report = true;
      cited.push({ id: fact.id, grade, field: fact.field, value: fact.value, stated });
    }
    if (!citation_ids.length) uncitedSegments++;
    segments.push({ text, citation_ids, cited, uncited_assertions: uncited, informative: true });
  }
  for (const f of facts) {
    const def = lx.findings.find((x) => x.id === f.field);
    f.referenced_in_thinking = !!def && aliasesOf(def).some((a) => lowR.includes(a));
    f.ignored = !f.cited_in_report && !f.referenced_in_thinking;
  }
  // answer and candidates
  const names = (e) => [e.display, ...(e.aliases ?? [])].filter(Boolean).map((a) => a.toLowerCase());
  const ansLower = (body.answer || '').toLowerCase();
  const ent = lx.entities.find((e) => names(e).some((a) => ansLower.includes(a))) ?? null;
  const decision = ent?.id ?? 'UNRESOLVED';
  const candidates = lx.entities.filter((e) => !e.parent).map((e) => e.id);
  const named = lx.entities.filter((e) => !e.parent && names(e).some((a) => lowR.includes(a))).map((e) => e.id);
  const truthEntity = body.entity || null;
  const ignored = facts.filter((f) => f.ignored);
  const checks = [];
  const check = (id, title, ok, detail = '') => checks.push({ id, title, status: ok ? 'PASS' : 'FAIL', detail });
  check('citations_exist', 'Every cited id exists', true);
  check('citations_agree', 'Cited facts are stated with their recorded value', disagree === 0, `${agree} agree, ${disagree} disagree, 0 unverifiable`);
  check('segments_cited', 'Every informative segment carries a citation', uncitedSegments === 0, `${uncitedSegments} informative segment(s) without citations`);
  check('nothing_dropped', 'Nothing informative deleted by post-processing', true);
  if (truthEntity) check('decision_matches_truth', 'Delivered answer matches ground truth', decision === truthEntity, `${decision} vs ${truthEntity}`);
  check('thinking_present', 'Thinking returned', reasoning.trim().length > 0, `${reasoning.length} characters`);
  check('thinking_considers_alternatives', 'Thinking considered more than one candidate answer', new Set(named).size > 1, 'named: ' + (named.join(', ') || 'none'));
  check('thinking_ids_valid', 'Thinking cites only allowed ids', true);
  check('thinking_agrees', 'Facts restated in thinking match their recorded values', disagree === 0);
  check('coverage', 'Every patient/context fact was referenced in thinking, report or rationale', ignored.length === 0, `${ignored.length} ignored, ${ignored.length} of them informative`);
  check('coverage_informative', 'Every informative patient/context fact was referenced', ignored.length === 0, ignored.slice(0, 12).map((f) => `${f.id} ${f.field}=${f.value}`).join(', '));
  const graded = agree + disagree;
  const metrics = {
    facts: facts.length, patient_facts: facts.length, context_facts: 0, reference_facts: 0,
    cited_in_report: facts.filter((f) => f.cited_in_report).length, cited_agree: agree, cited_disagree: disagree, cited_unverifiable: 0,
    uncited_assertions: uncitedAssertions, grounding_rate: graded ? agree / graded : null,
    thinking_chars: reasoning.length, thinking_ids: 0, thinking_fields: facts.filter((f) => f.referenced_in_thinking).length,
    candidates_named_in_thinking: Object.fromEntries(named.map((c) => [c, 1])), ignored: ignored.length, ignored_informative: ignored.length,
    checks_failed: checks.filter((c) => c.status === 'FAIL').length, checks_total: checks.length,
  };
  return {
    case_id: 'ANL-001', truth: truthEntity, decision, candidates, checks, metrics,
    sections: [{ title: 'Factual claims', segments }], facts,
    thinking: { text: reasoning, ids: [], candidates: named }, rationale: null, ablation: null,
    documents: docs.map((d) => ({ ...d, facts: Object.entries(spans).filter(([, sp]) => sp.report === d.id).map(([id, sp]) => ({ id, start: sp.start, end: sp.end })) })),
    answer: { text: body.answer || '', entity: decision, entity_raw: ent?.display ?? null, subtype: null, hedged: /\b(maybe|possibly|might|unsure|indeterminate)\b/i.test(body.answer || ''), entities_named: ent ? [ent.id] : [], claims: nClaims, factual_claims: segments.length },
  };
}

async function analyse(body) {
  if (!body.lexicon_id || typeof body.lexicon_id !== 'string') return [400, { error: { code: 'lexicon_required', message: 'lexicon_id is required: choose an example lexicon or upload one' } }];
  const lx = lexicons.get(body.lexicon_id);
  if (!lx) return [404, { error: { code: 'lexicon_not_found', message: `unknown lexicon ${body.lexicon_id}` } }];
  const documents = body.documents && typeof body.documents === 'object' ? body.documents : {};
  const known = Object.fromEntries(lx.sections.map((sec) => [sec.id, sec.title]));
  const sections = Object.keys(documents).length ? Object.keys(documents).map((k) => ({ id: k, title: body.titles?.[k] || known[k] || cap(k) })) : lx.sections;
  if (Object.keys(documents).length > 20) return [400, { error: { code: 'bad_request', message: 'at most 20 documents' } }];
  for (const [k, v] of Object.entries(documents)) {
    if (typeof v !== 'string') return [400, { error: { code: 'bad_request', message: `document ${k} must be a string` } }];
    if (v.length > 50_000) return [400, { error: { code: 'too_large', message: `document ${k} exceeds 50 KB` } }];
  }
  if (!Object.values(documents).some((v) => v && v.trim())) return [400, { error: { code: 'bad_request', message: 'documents must contain at least one of ' + lx.sections.map((sec) => sec.id).join(', ') } }];
  if (typeof body.reasoning !== 'string' || !body.reasoning.trim()) return [400, { error: { code: 'bad_request', message: 'reasoning is required: paste the model\'s reasoning text' } }];
  if (body.reasoning.length > 200_000) return [400, { error: { code: 'too_large', message: 'reasoning exceeds 200 KB' } }];
  if (typeof body.answer !== 'string' || !body.answer.trim()) return [400, { error: { code: 'bad_request', message: 'answer is required: paste the model\'s final answer' } }];
  const oracle = body.truth && typeof body.truth === 'object' && Object.keys(body.truth).length ? 'truth' : 'extracted';
  const lexiconOut = { id: lx.id, domain: lx.domain, version: lx.version, entities: lx.entities.map((e) => ({ id: e.id, display: e.display })), findings: lx.findings.map((f) => ({ id: f.id, display: f.display, kind: f.kind })) };
  // The packaged example, unchanged, gets the real service's answer so the page shows exactly what `traceaudit serve` returns.
  if (lx.id === 'example:incident-triage' && oracle === 'extracted' && !body.entity) {
    const canned = JSON.parse(await readFile(ANALYSE_FIXTURE, 'utf8'));
    if (canned.thinking?.text === body.reasoning && canned.documents.every((d) => (documents[d.id] || '') === d.text)) return [200, { ...canned, lexicon: { ...canned.lexicon, id: lx.id } }];
  }
  const r = genericAnalyse(body, lx, documents, sections, oracle);
  return [200, { ...r, lexicon: lexiconOut, oracle, warnings: [], lexicon_version: lx.version, domain: lx.domain }];
}

// ---- jobs ----------------------------------------------------------------------------------------

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
  jobs.set(job_id, { job, polls: 0, bundle: null });
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
    // The scored bundle: the synthetic incident-triage fixture under this job's run id.
    const runId = `${job.finished.replace(/[-:]/g, '').slice(0, 15)}Z-${job.job_id.slice(4, 10)}`;
    entry.bundle = makeIncidentBundle({ runId, generated: job.finished, study: false });
    const s = entry.bundle.index.summary;
    job.headline = {
      traces: s.counts.traces, errors: job.progress.errors, grounding_rate: s.grounding.pooled_rate.point,
      silent_rate: s.counterfactual?.decisive?.silent_rate.point ?? null, spurious_rate: s.counterfactual?.neutral?.spurious_rate.point ?? null,
      silent_shift_rate: s.authority?.wrong?.silent_shift_rate.point ?? null,
    };
  }
}

function bundleFile(entry, rel) {
  const { index, caseFile } = entry.bundle;
  if (rel === 'index.json') return index;
  const m = /^cases\/([^/]+)\.json$/.exec(rel);
  if (m && m[1] === caseFile.case.case_id) return caseFile;
  return null;
}

function cannedFile(entry, name) {
  const { index, caseFile } = entry.bundle;
  const traces = caseFile.traces;
  switch (name) {
    case 'summary.json': return [JSON.stringify(index.summary, null, 1), MIME['.json']];
    case 'manifest.json': return [JSON.stringify(index.run.manifest, null, 1), MIME['.json']];
    case 'report.md': return [`# traceaudit report (mock)\n\nRun ${index.run.run_id}\n\n- traces: ${index.summary.counts.traces}\n- pooled grounding rate: ${index.summary.grounding?.pooled_rate?.point ?? 'n/a'}\n`, MIME['.md']];
    case 'traces.jsonl': return [traces.map((t) => JSON.stringify({ trace_key: t.trace_key, effort: t.effort, run: t.run, answer: t.answer })).join('\n') + '\n', MIME['.jsonl']];
    case 'long.csv': return ['trace_key,effort,run,grounding_rate\n' + traces.map((t) => `${t.trace_key},${t.effort},${t.run},${t.grounding?.grounding_rate ?? ''}`).join('\n') + '\n', MIME['.csv']];
    default: return null;
  }
}

// ---- server --------------------------------------------------------------------------------------

await loadExampleLexicons();

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
      if (req.method === 'GET' && path === '/api/lexicons') {
        const all = [...lexicons.values()];
        return sendJson(res, 200, [...all.filter((l) => l.source === 'example'), ...all.filter((l) => l.source !== 'example')].map(lexiconMeta));
      }
      if (req.method === 'POST' && path === '/api/lexicons') {
        let body;
        try { body = JSON.parse(await readBody(req) || '{}'); } catch { return sendError(res, 400, 'bad_json', 'Request body is not valid JSON'); }
        const [code, out] = uploadLexicon(body);
        return sendJson(res, code, out);
      }
      if (req.method === 'GET' && path === '/api/case-sets') return sendJson(res, 200, CASE_SETS);
      if (req.method === 'POST' && path === '/api/uploads') {
        let body;
        try { body = JSON.parse(await readBody(req) || '{}'); } catch { return sendError(res, 400, 'bad_json', 'Request body is not valid JSON'); }
        const [code, out] = createUpload(body);
        return sendJson(res, code, out);
      }
      if (req.method === 'POST' && path === '/api/ledger') {
        let body;
        try { body = JSON.parse(await readBody(req) || '{}'); } catch { return sendError(res, 400, 'bad_json', 'Request body is not valid JSON'); }
        const hasMarkdown = typeof body.markdown === 'string' && body.markdown.trim();
        const hasStructured = body.case && typeof body.case === 'object' && body.trace && typeof body.trace === 'object';
        if (!hasMarkdown && !hasStructured) return sendError(res, 400, 'bad_request', 'Send {markdown} (the trace artefact text) or {case, trace}');
        const canned = JSON.parse(await readFile(LEDGER_FIXTURE, 'utf8'));
        return sendJson(res, 200, canned);
      }
      if (req.method === 'POST' && path === '/api/analyse') {
        let body;
        try { body = JSON.parse(await readBody(req) || '{}'); } catch { return sendError(res, 400, 'bad_json', 'Request body is not valid JSON'); }
        const [code, out] = await analyse(body);
        return sendJson(res, code, out);
      }
      if (req.method === 'POST' && path === '/api/jobs') {
        let body;
        try { body = JSON.parse(await readBody(req) || '{}'); } catch { return sendError(res, 400, 'bad_json', 'Request body is not valid JSON'); }
        const [code, out] = createJob(body);
        return sendJson(res, code, out);
      }
      if (req.method === 'GET' && path === '/api/jobs') {
        const list = [...jobs.values()].sort((a, b) => b.job.created.localeCompare(a.job.created)).map(({ job }) => ({ job_id: job.job_id, status: job.status, created: job.created, progress: job.progress, headline: job.headline ?? undefined }));
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
          if (entry.job.status !== 'done' || !entry.bundle) return sendError(res, 409, 'not_ready', `Job ${entry.job.job_id} is ${entry.job.status}; the bundle is written when it is done`);
          const rel = rest.slice('bundle/'.length) || 'index.json';
          const out = bundleFile(entry, rel);
          return out ? sendJson(res, 200, out) : sendError(res, 404, 'not_found', `No such file in the bundle: ${rel}`);
        }
        if (req.method === 'GET' && rest.startsWith('files/')) {
          if (entry.job.status !== 'done' || !entry.bundle) return sendError(res, 409, 'not_ready', `Job ${entry.job.job_id} is ${entry.job.status}; files are written when it is done`);
          const name = rest.slice('files/'.length);
          const f = cannedFile(entry, name);
          return f ? sendText(res, f[0], f[1], name) : sendError(res, 404, 'not_found', `No file ${name}`);
        }
      }
      return sendError(res, 404, 'not_found', `No endpoint ${req.method} ${path}`);
    } catch (e) {
      return sendError(res, 500, 'internal', e instanceof Error ? e.message : String(e));
    }
  }

  // Static: the built viewer when present (so ?bundle=/api/jobs/<id>/bundle/ is same-origin), and the examples.
  if (req.method === 'GET' && existsSync(DIST)) {
    const rel = path === '/' ? 'index.html' : decodeURIComponent(path.slice(1));
    const p = safeJoin(DIST, rel);
    if (p && existsSync(p)) return sendFile(res, p);
  }
  if (req.method === 'GET' && path.startsWith('/examples/')) {
    const p = safeJoin(EXAMPLES, decodeURIComponent(path.slice('/examples/'.length)));
    if (p) return sendFile(res, p);
  }
  sendError(res, 404, 'not_found', `Nothing at ${path} (build the viewer with npm run build to serve it here)`);
});

server.listen(PORT, '127.0.0.1', () => {
  console.log(`traceaudit mock service on http://127.0.0.1:${PORT}  (token: ${TOKEN ? 'required' : 'none'}; static: ${existsSync(DIST) ? 'dist/' : 'none'}; lexicons: ${[...lexicons.keys()].join(', ')})`);
});
