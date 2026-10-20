import { describe, expect, it } from 'vitest';
import { buildSingleTraceBundle } from '../lib/analyseBundle';
import type { AnalyseRequest, AnalyseResponse } from '../lib/api';
import { buildConstellation } from '../constellation/graph';
import { claimEvidenceHighlights } from '../lib/evidence';
import { validateIndex } from '../lib/bundle';
import { makeIncidentBundle, CASE_ID } from './fixtures/incidentBundle';

const { index, caseFile: inc, raw } = makeIncidentBundle();
const trace = inc.traces.find((t) => t.variant === 'base' && t.effort === 'high')!;

// What the service returns for the example inputs (the mock grades the same way).
const req: AnalyseRequest = {
  documents: inc.variants.base.reports,
  titles: Object.fromEntries(raw.sections.map((s) => [s.id, s.title])),
  reasoning: trace.reasoning, answer: trace.answer, entity: inc.case.entity, lexicon_id: 'example:incident-triage',
};
const res: AnalyseResponse = {
  case: { case_id: inc.case.case_id, entity: inc.case.entity, reports: inc.case.reports, truth: inc.case.truth, finding_spans: inc.case.finding_spans, sections: raw.sections },
  claims: trace.claims,
  grounding: trace.grounding,
  map: trace.map,
  parsed_answer: { entity: trace.grounding?.answer_entity ?? null, hedged: false, confidence: 'high' },
  oracle: 'extracted',
  lexicon: { id: 'example:incident-triage', domain: raw.domain, version: raw.version, entities: index.lexicon.entities.map((e) => ({ id: e.id, display: e.display })), findings: index.lexicon.findings },
  domain: raw.domain,
};

describe('buildSingleTraceBundle', () => {
  it('builds a one-case, one-variant, one-trace bundle the loaders and views accept', async () => {
    const built = buildSingleTraceBundle(req, res, index.lexicon, { now: new Date('2026-10-20T12:00:00Z') });
    expect(built.traceKey).toBe(`${CASE_ID}|base|medium|0`);
    expect(built.trace.trace_key).toBe(built.traceKey);
    expect(built.trace.claims.every((c) => c.trace_key === built.traceKey)).toBe(true);
    expect(built.trace.grounding?.trace_key).toBe(built.traceKey);
    expect(built.trace.grounding?.effort).toBe('medium');
    expect(built.caseFile.variants.base.reports).toEqual(inc.case.reports);
    expect(built.caseFile.case.finding_spans).toBe(inc.case.finding_spans);
    expect(built.caseFile.case.sections).toEqual(raw.sections);
    expect(built.caseFile.traces).toHaveLength(1);
    // The index passes the same validation as a real export.
    const idx = validateIndex(built.bundle.index);
    expect(idx.cases).toEqual([expect.objectContaining({ case_id: CASE_ID, variants: ['base'], n_traces: 1, file: `cases/${CASE_ID}.json` })]);
    expect(idx.run.run_id).toBe('analyse-20261020T120000Z');
    expect(idx.run.manifest.notes).toContain('domain: incident-triage');
    expect(idx.summary.counts.traces).toBe(1);
    expect(idx.summary.grounding.pooled_rate.point).toBe(trace.grounding?.grounding_rate);
    expect(idx.lexicon.version).toBe(index.lexicon.version);
    expect(idx.lexicon.entities.find((e) => e.id === 'BAD_DEPLOY')?.display).toBe('Faulty deployment');
    await expect(built.bundle.loadCase(CASE_ID)).resolves.toBe(built.caseFile);
    await expect(built.bundle.loadCase('nope')).rejects.toThrow(/Unknown case/);
    expect(built.bundle.cases.get(CASE_ID)).toBe(built.caseFile);
  });

  it('keeps claim offsets aligned with the submitted reasoning and feeds the grounding components', () => {
    const built = buildSingleTraceBundle(req, res, index.lexicon);
    for (const c of built.trace.claims) expect(built.trace.reasoning.slice(c.start, c.end)).toBe(c.text);
    const contradicted = built.trace.claims.find((c) => c.label === 'contradicted')!;
    const ev = claimEvidenceHighlights(contradicted, built.caseFile.variants.base.reports, built.caseFile.case.finding_spans);
    expect(ev.highlights.length + ev.notInInputs.length).toBeGreaterThan(0);
    expect(ev.highlights[0]?.kind).toBe('contradicted');
    const supported = built.trace.claims.find((c) => c.label === 'supported')!;
    const evS = claimEvidenceHighlights(supported, built.caseFile.variants.base.reports, built.caseFile.case.finding_spans);
    expect(evS.highlights[0]?.kind).toBe('supported');
    const graph = buildConstellation(built.trace, built.caseFile, built.bundle.index.lexicon, { truthEntity: built.caseFile.case.entity });
    expect(graph.nodes.some((n) => n.band === 0)).toBe(true);
    expect(graph.nodes.filter((n) => n.band === 1).length).toBe(trace.map!.nodes.filter((n) => n.type !== 'answer').length);
    expect(graph.nodes.some((n) => n.band === 2 && n.entity === 'BAD_DEPLOY')).toBe(true);
    expect(graph.edges.some((e) => e.kind === 'reads')).toBe(true);
  });

  it('falls back to the request when the response carries no case, and to the caller lexicon when it carries none', () => {
    const bare: AnalyseResponse = { case: null as unknown as AnalyseResponse['case'], claims: [], grounding: null, map: null, parsed_answer: null, oracle: 'extracted' };
    const built = buildSingleTraceBundle({ documents: { alerts: 'a', logs: '' }, titles: { alerts: 'Alerts', logs: 'Logs' }, reasoning: 'r', answer: 'a', lexicon_id: 'x' }, bare, { version: 'v9', entities: [], findings: [] });
    expect(built.traceKey).toBe('analysed|base|medium|0');
    expect(Object.keys(built.caseFile.case.reports)).toEqual(['alerts', 'logs']);
    expect(built.caseFile.case.sections).toEqual([{ id: 'alerts', title: 'Alerts' }, { id: 'logs', title: 'Logs' }]);
    expect(built.caseFile.case.flags.missing_modalities).toEqual(['logs']);
    expect(built.bundle.index.lexicon.version).toBe('v9');
    expect(built.bundle.index.summary.grounding.pooled_rate.point).toBeNull();
  });
});
