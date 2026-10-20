import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { buildSingleTraceBundle } from '../lib/analyseBundle';
import type { AnalyseRequest, AnalyseResponse } from '../lib/api';
import { buildConstellation } from '../constellation/graph';
import { claimEvidenceHighlights } from '../lib/evidence';
import { validateIndex } from '../lib/bundle';
import type { BundleIndex, CaseFile } from '../types';

const demo = resolve(__dirname, '../../public/demo');
const index = JSON.parse(readFileSync(resolve(demo, 'index.json'), 'utf8')) as BundleIndex;
const cll = JSON.parse(readFileSync(resolve(demo, 'cases/CLL-001.json'), 'utf8')) as CaseFile;
const trace = cll.traces.find((t) => t.variant === 'base' && t.effort === 'high' && t.run === 0)!;

// What the mock (and the real service) returns for the example inputs.
const req: AnalyseRequest = { reports: cll.variants.base.reports, reasoning: trace.reasoning, answer: trace.answer, entity: cll.case.entity };
const res: AnalyseResponse = {
  case: { case_id: cll.case.case_id, entity: cll.case.entity, reports: cll.case.reports, truth: cll.case.truth, finding_spans: cll.case.finding_spans },
  claims: trace.claims,
  grounding: trace.grounding,
  map: trace.map,
  parsed_answer: { entity: trace.grounding?.answer_entity ?? null, hedged: false, confidence: 'high' },
  oracle: 'extracted',
};

describe('buildSingleTraceBundle', () => {
  it('builds a one-case, one-variant, one-trace bundle the loaders and views accept', async () => {
    const built = buildSingleTraceBundle(req, res, index.lexicon, { now: new Date('2026-10-20T12:00:00Z') });
    expect(built.traceKey).toBe('CLL-001|base|medium|0');
    expect(built.trace.trace_key).toBe(built.traceKey);
    expect(built.trace.claims.every((c) => c.trace_key === built.traceKey)).toBe(true);
    expect(built.trace.grounding?.trace_key).toBe(built.traceKey);
    expect(built.trace.grounding?.effort).toBe('medium');
    expect(built.caseFile.variants.base.reports).toEqual(cll.case.reports);
    expect(built.caseFile.case.finding_spans).toBe(cll.case.finding_spans);
    expect(built.caseFile.traces).toHaveLength(1);
    // The index passes the same validation as a real export.
    const idx = validateIndex(built.bundle.index);
    expect(idx.cases).toEqual([expect.objectContaining({ case_id: 'CLL-001', variants: ['base'], n_traces: 1, file: 'cases/CLL-001.json' })]);
    expect(idx.run.run_id).toBe('analyse-20261020T120000Z');
    expect(idx.summary.counts.traces).toBe(1);
    expect(idx.summary.grounding.pooled_rate.point).toBe(trace.grounding?.grounding_rate);
    expect(idx.lexicon.version).toBe(index.lexicon.version);
    await expect(built.bundle.loadCase('CLL-001')).resolves.toBe(built.caseFile);
    await expect(built.bundle.loadCase('nope')).rejects.toThrow(/Unknown case/);
    expect(built.bundle.cases.get('CLL-001')).toBe(built.caseFile);
  });

  it('keeps claim offsets aligned with the submitted reasoning and feeds the grounding components', () => {
    const built = buildSingleTraceBundle(req, res, index.lexicon);
    for (const c of built.trace.claims) expect(built.trace.reasoning.slice(c.start, c.end)).toBe(c.text);
    const contradicted = built.trace.claims.find((c) => c.label === 'contradicted')!;
    const ev = claimEvidenceHighlights(contradicted, built.caseFile.variants.base.reports, built.caseFile.case.finding_spans);
    expect(ev.highlights.length + ev.notInInputs.length).toBeGreaterThan(0);
    const supported = built.trace.claims.find((c) => c.label === 'supported')!;
    const evS = claimEvidenceHighlights(supported, built.caseFile.variants.base.reports, built.caseFile.case.finding_spans);
    expect(evS.highlights[0]?.kind).toBe('supported');
    const graph = buildConstellation(built.trace, built.caseFile, built.bundle.index.lexicon, { truthEntity: built.caseFile.case.entity });
    expect(graph.nodes.some((n) => n.band === 0)).toBe(true);
    expect(graph.nodes.filter((n) => n.band === 1).length).toBe(trace.map!.nodes.filter((n) => n.type !== 'answer').length);
    expect(graph.nodes.some((n) => n.band === 2 && n.entity === 'CLL_SLL')).toBe(true);
    expect(graph.edges.some((e) => e.kind === 'reads')).toBe(true);
  });

  it('copes with a sparse response: no grounding, no map, missing reports, unknown case id', () => {
    const sparse: AnalyseResponse = { case: { case_id: '', entity: null, reports: { clinical: 'Lymphocytosis.' } as never, truth: {}, finding_spans: {} }, claims: [], grounding: null, map: null, parsed_answer: null, oracle: 'extracted' };
    const built = buildSingleTraceBundle({ reports: { clinical: 'Lymphocytosis.' }, reasoning: 'x', answer: 'y' }, sparse, { version: 'v', entities: [], findings: [] }, { effort: 'low' });
    expect(built.traceKey).toBe('analysed|base|low|0');
    // Only the documents that were sent or returned exist; the one known key gets its built-in title.
    expect(Object.keys(built.caseFile.case.reports)).toEqual(['clinical']);
    expect(built.caseFile.case.sections).toEqual([{ id: 'clinical', title: 'Clinical summary' }]);
    expect(built.caseFile.case.flags.missing_modalities).toEqual([]);
    expect(built.caseFile.case.entity).toBe('unknown');
    expect(built.bundle.index.summary.grounding.pooled_rate.point).toBeNull();
    const graph = buildConstellation(built.trace, built.caseFile, built.bundle.index.lexicon);
    expect(graph.nodes.filter((n) => n.band === 2)).toHaveLength(1);
  });
});
