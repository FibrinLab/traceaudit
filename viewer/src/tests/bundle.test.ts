import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it, vi } from 'vitest';
import { bundleFromSingleObject, loadBundleFromUrl, validateIndex, BundleError } from '../lib/bundle';
import { parseTraceKey, variantKindOf } from '../types';

const demo = resolve(__dirname, '../../public/demo');
const indexJson = JSON.parse(readFileSync(resolve(demo, 'index.json'), 'utf8'));
const cll = JSON.parse(readFileSync(resolve(demo, 'cases/CLL-001.json'), 'utf8'));

describe('validateIndex', () => {
  it('accepts the real demo index and normalises optional blocks', () => {
    const idx = validateIndex(indexJson);
    expect(idx.bundle_version).toBe(1);
    expect(idx.run.run_id).toMatch(/^\d{8}T\d{6}Z-[a-z0-9]{6}$/);
    expect(idx.cases.length).toBeGreaterThan(0);
    expect(idx.rubric.dimensions.map((d) => d.id)).toEqual(['D1', 'D2', 'D3', 'D4', 'D5', 'D6', 'D7']);
    expect(idx.study?.rating_set.length).toBe(12);
    expect(idx.ratings).toBeNull();
    expect(idx.summary.counts.traces).toBe(297);
  });
  it('rejects a newer bundle_version and malformed input', () => {
    expect(() => validateIndex({ ...indexJson, bundle_version: 99 })).toThrow(BundleError);
    expect(() => validateIndex({})).toThrow(BundleError);
    expect(() => validateIndex(null)).toThrow(BundleError);
  });
});

describe('loadBundleFromUrl', () => {
  it('fetches index.json then case files lazily and caches them', async () => {
    const calls: string[] = [];
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      calls.push(url);
      if (url.endsWith('index.json')) return new Response(JSON.stringify(indexJson), { status: 200 });
      if (url.endsWith('cases/CLL-001.json')) return new Response(JSON.stringify(cll), { status: 200 });
      return new Response('nope', { status: 404 });
    }));
    const b = await loadBundleFromUrl('./demo/');
    expect(calls).toEqual(['./demo/index.json']);
    expect(b.cases.size).toBe(0);
    const cf = await b.loadCase('CLL-001');
    expect(cf.case.case_id).toBe('CLL-001');
    expect(cf.traces.length).toBe(54);
    await b.loadCase('CLL-001');
    expect(calls.filter((c) => c.includes('CLL-001')).length).toBe(1);
    await expect(b.loadCase('FL-001')).rejects.toThrow(/HTTP 404/);
    await expect(b.loadCase('NOPE-999')).rejects.toThrow(/Unknown case/);
    vi.unstubAllGlobals();
  });
});

describe('bundleFromSingleObject', () => {
  it('serves cases from an un-sharded bundle.json', async () => {
    const b = bundleFromSingleObject({ index: indexJson, cases: { 'CLL-001': cll } }, 'bundle.json');
    const cf = await b.loadCase('CLL-001');
    expect(cf.variants.base.kind).toBe('base');
    await expect(b.loadCase('FL-001')).rejects.toThrow(/lacks case/);
    expect(() => bundleFromSingleObject({ index: indexJson }, 'x')).toThrow(BundleError);
  });
});

describe('types against real data', () => {
  it('trace shapes match what the viewer relies on', () => {
    const t = cll.traces.find((x: { variant: string }) => x.variant === 'dec-cyclin_d1');
    expect(t.counterfactual.outcome).toBeDefined();
    expect(typeof t.counterfactual.cited_primary).toBe('boolean');
    for (const c of t.claims) {
      expect(c.end).toBeGreaterThanOrEqual(c.start);
      expect(t.reasoning.slice(c.start, c.end)).toBe(c.text);
    }
    expect(t.map.nodes.some((n: { type: string }) => n.type === 'answer')).toBe(true);
    expect(parseTraceKey(t.trace_key)).toEqual({ case_id: 'CLL-001', variant: 'dec-cyclin_d1', effort: t.effort, run: t.run });
    expect(variantKindOf('dec-cyclin_d1')).toBe('decisive');
    expect(variantKindOf('anc-cd23')).toBe('anchor_loss');
    expect(variantKindOf('neu-1')).toBe('neutral');
    expect(variantKindOf('auth-wrong-mcl')).toBe('authority');
    expect(variantKindOf('base')).toBe('base');
  });
  it('diff spans point at the before/after text', () => {
    for (const v of Object.values(cll.variants) as Array<{ reports: Record<string, string>; diff: Record<string, Array<{ base_span: [number, number]; variant_span: [number, number]; before: string; after: string }>> }>) {
      for (const [report, ops] of Object.entries(v.diff)) {
        for (const op of ops) {
          expect(cll.variants.base.reports[report].slice(op.base_span[0], op.base_span[1])).toBe(op.before);
          expect(v.reports[report].slice(op.variant_span[0], op.variant_span[1])).toBe(op.after);
        }
      }
    }
  });
});
