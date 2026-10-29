import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render } from '@testing-library/react';
import { FACT_STATUS_TEXT, analyseExport, documentHighlights, factStatus, parseAnalyseResponse } from '../lib/analyse';
import { createApi } from '../lib/api';
import { ReportPane } from '../components/ReportPane';
import { LedgerResultView } from '../views/AnalyseLedgerView';

// What `traceaudit serve` returns for examples/incident-trace.json on the incident-triage lexicon.
import raw from '../../mock/fixtures/analyse-result.json';

describe('parseAnalyseResponse', () => {
  const res = parseAnalyseResponse(raw);
  it('is a ledger result plus the documents, answer, headline and oracle', () => {
    expect(res.decision).toBe('BAD_DEPLOY');
    expect(res.truth).toBeNull();
    expect(res.candidates).toEqual(['BAD_DEPLOY', 'CAPACITY', 'DATABASE', 'DISK']);
    expect(res.checks.map((c) => c.id)).toContain('citations_agree');
    expect(res.metrics.cited_agree).toBe(3);
    expect(res.metrics.cited_disagree).toBe(1);
    expect(res.headline).toEqual({ grounding_rate: 0.75, uncited_assertions: 0 });
    expect(res.oracle).toBe('extracted');
    expect(res.domain).toBe('incident-triage');
    expect(res.lexicon?.findings.find((f) => f.id === 'cpu_saturated')?.display).toBe('CPU saturated');
    expect(res.answer).toMatchObject({ entity: 'BAD_DEPLOY', entity_raw: 'faulty deployment', hedged: false, claims: 3, factual_claims: 3 });
    expect(res.sections).toHaveLength(1);
    expect(res.sections[0].segments.map((s) => s.cited.map((c) => c.grade))).toEqual([['agree', 'agree'], ['disagree'], ['agree']]);
    expect(res.thinking?.candidates).toEqual(['CAPACITY', 'DATABASE']);
    expect(res.rationale).toBeNull();
    expect(res.ablation).toBeNull();
  });
  it('carries every fact\'s evidence span into its document', () => {
    expect(res.documents.map((d) => d.id)).toEqual(['alerts', 'logs', 'deploys']);
    const facts = new Map(res.facts.map((f) => [f.id, f]));
    let n = 0;
    for (const d of res.documents) for (const sp of d.facts) { n++; expect(d.text.slice(sp.start, sp.end)).toBe(facts.get(sp.id)?.evidence); }
    expect(n).toBe(res.facts.length);
    expect(res.facts[0]).toMatchObject({ id: 'p_1', source: 'patient', section: 'alerts', field: 'error_rate_elevated', value: 'Positive', evidence: 'Error rate elevated' });
  });
  it('rejects responses without documents and tolerates missing optional parts', () => {
    expect(() => parseAnalyseResponse({ ...raw, documents: 'no' })).toThrow(/documents/);
    const minimal = parseAnalyseResponse({ decision: 'A', truth: null, checks: [], facts: [], documents: [{ id: 'notes', text: 'x' }] });
    expect(minimal.documents).toEqual([{ id: 'notes', title: 'notes', text: 'x', facts: [] }]);
    expect(minimal.headline).toEqual({ grounding_rate: null, uncited_assertions: 0 });
    expect(minimal.answer).toBeNull();
    expect(minimal.lexicon).toBeNull();
    expect(minimal.warnings).toEqual([]);
  });
  it('is what the api client resolves to', async () => {
    const fn = vi.fn(async () => new Response(JSON.stringify(raw), { status: 200, headers: { 'Content-Type': 'application/json' } }));
    const api = createApi({ base: '', token: '' }, fn as unknown as typeof fetch);
    const out = await api.analyse({ documents: {}, reasoning: 'r', answer: 'a', lexicon_id: 'example:incident-triage' });
    expect(out.decision).toBe('BAD_DEPLOY');
    expect(out.documents).toHaveLength(3);
    expect(analyseExport({ reasoning: 'r' }, out, { api_base: 'same origin', lexicon_version: '0.1.0', analysed_at: 't' })).toMatchObject({ schema: 'traceaudit-analyse-result/2', response: { decision: 'BAD_DEPLOY' } });
  });
});

describe('document highlights', () => {
  const res = parseAnalyseResponse(raw);
  it('colours each fact by how the reasoning treated it', () => {
    const status = Object.fromEntries(res.facts.map((f) => [f.id, factStatus(f, res.sections)]));
    expect(status).toEqual({ p_1: 'agree', p_2: 'referenced', p_3: 'disagree', p_4: 'ignored', p_5: 'agree', p_6: 'ignored', p_7: 'agree' });
    const hs = documentHighlights(res, { findingDisplay: (f) => res.lexicon?.findings.find((x) => x.id === f)?.display ?? f });
    expect(hs).toHaveLength(7);
    expect(hs.find((h) => h.id === 'p_3')).toMatchObject({ report: 'alerts', kind: 'contradicted', title: `p_3 · CPU saturated = Negative · ${FACT_STATUS_TEXT.disagree}` });
    expect(hs.find((h) => h.id === 'p_4')?.kind).toBe('other');
    expect(hs.find((h) => h.id === 'p_2')?.kind).toBe('mention');
    expect(documentHighlights(res, { highlight: 'p_1' }).find((h) => h.id === 'p_1')).toMatchObject({ kind: 'focus', priority: 2 });
  });
  it('clicking a highlight reports the fact id', () => {
    const onClick = vi.fn();
    const reports = Object.fromEntries(res.documents.map((d) => [d.id, d.text]));
    const { container } = render(<ReportPane reports={reports} sections={res.documents} highlights={documentHighlights(res)} onHighlightClick={onClick} />);
    const mark = container.querySelector<HTMLElement>('mark[data-hl-id="p_3"]')!;
    expect(mark.getAttribute('role')).toBe('button');
    expect(mark.textContent).toContain('CPU normal');
    fireEvent.click(mark);
    fireEvent.keyDown(mark, { key: 'Enter' });
    expect(onClick.mock.calls).toEqual([['p_3'], ['p_3']]);
  });
  it('renders inside the ledger result view as the lead block', () => {
    const { container } = render(<LedgerResultView result={res} lead={(ctx) => <div id="lead">{ctx.facts.size} facts</div>} />);
    const blocks = [...container.querySelectorAll('section.ledger-block')].map((s) => s.id);
    expect(container.querySelector('#lead')?.textContent).toBe('7 facts');
    expect(blocks.slice(0, 3)).toEqual(['ledger-verdict', 'ledger-report', 'ledger-ledger']);
    expect(container.textContent).toContain('Factual claims');
    expect(container.querySelectorAll('tr.fact-row')).toHaveLength(7);
    expect(blocks).toContain('ledger-rationale');
    const hidden = render(<LedgerResultView result={res} hideAbsent />);
    expect([...hidden.container.querySelectorAll('section.ledger-block')].map((s) => s.id)).toEqual(['ledger-verdict', 'ledger-report', 'ledger-ledger', 'ledger-reasoning', 'ledger-coverage']);
  });
});
