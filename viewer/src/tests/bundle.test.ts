import { describe, expect, it, vi } from 'vitest';
import { bundleFromSingleObject, loadBundleFromUrl, validateIndex, BundleError } from '../lib/bundle';
import { parseTraceKey, variantKindOf } from '../types';
import { makeIncidentBundle, CASE_ID } from './fixtures/incidentBundle';

const { index: indexJson, caseFile: inc } = makeIncidentBundle({ study: true });

describe('validateIndex', () => {
  it('accepts the synthetic index and normalises optional blocks', () => {
    const idx = validateIndex(indexJson);
    expect(idx.bundle_version).toBe(1);
    expect(idx.run.run_id).toMatch(/^\d{8}T\d{6}Z-[a-z0-9]{6}$/);
    expect(idx.cases.length).toBe(1);
    expect(idx.rubric.dimensions.map((d) => d.id)).toEqual(['D1', 'D2', 'D3', 'D4', 'D5', 'D6', 'D7']);
    expect(idx.study?.rating_set.length).toBe(6);
    expect(idx.ratings).toBeNull();
    expect(idx.summary.counts.traces).toBe(18);
    expect(validateIndex({ ...indexJson, study: undefined, ratings: undefined }).study).toBeNull();
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
    // A second case that the server does not have, to exercise the HTTP error path.
    const withMissing = { ...indexJson, cases: [...indexJson.cases, { ...indexJson.cases[0], case_id: 'INC-404', file: 'cases/INC-404.json' }] };
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      calls.push(url);
      if (url.endsWith('index.json')) return new Response(JSON.stringify(withMissing), { status: 200 });
      if (url.endsWith(`cases/${CASE_ID}.json`)) return new Response(JSON.stringify(inc), { status: 200 });
      return new Response('nope', { status: 404 });
    }));
    const b = await loadBundleFromUrl('./run/');
    expect(calls).toEqual(['./run/index.json']);
    expect(b.cases.size).toBe(0);
    const cf = await b.loadCase(CASE_ID);
    expect(cf.case.case_id).toBe(CASE_ID);
    expect(cf.traces.length).toBe(18);
    await b.loadCase(CASE_ID);
    expect(calls.filter((c) => c.includes(CASE_ID)).length).toBe(1);
    await expect(b.loadCase('INC-404')).rejects.toThrow(/HTTP 404/);
    await expect(b.loadCase('NOPE-999')).rejects.toThrow(/Unknown case/);
    vi.unstubAllGlobals();
  });
});

describe('bundleFromSingleObject', () => {
  it('serves cases from an un-sharded bundle.json', async () => {
    const withMissing = { ...indexJson, cases: [...indexJson.cases, { ...indexJson.cases[0], case_id: 'INC-002', file: 'cases/INC-002.json' }] };
    const b = bundleFromSingleObject({ index: withMissing, cases: { [CASE_ID]: inc } }, 'bundle.json');
    const cf = await b.loadCase(CASE_ID);
    expect(cf.variants.base.kind).toBe('base');
    await expect(b.loadCase('INC-002')).rejects.toThrow(/lacks case/);
    expect(() => bundleFromSingleObject({ index: indexJson }, 'x')).toThrow(BundleError);
  });
});

describe('types against the synthetic data', () => {
  it('trace shapes match what the viewer relies on', () => {
    const t = inc.traces.find((x) => x.variant === 'dec-recent_deploy' && x.effort === 'high')!;
    expect(t.counterfactual!.outcome).toBe('disclosed');
    expect(typeof t.counterfactual!.cited_primary).toBe('boolean');
    for (const tr of inc.traces) for (const c of tr.claims) {
      expect(c.end).toBeGreaterThanOrEqual(c.start);
      expect(tr.reasoning.slice(c.start, c.end)).toBe(c.text);
      for (const a of c.assertions) expect(tr.reasoning.slice(a.start, a.end)).toBe(a.surface);
    }
    expect(t.map!.nodes.some((n) => n.type === 'answer')).toBe(true);
    expect(parseTraceKey(t.trace_key)).toEqual({ case_id: CASE_ID, variant: 'dec-recent_deploy', effort: t.effort, run: t.run });
    expect(variantKindOf('dec-recent_deploy')).toBe('decisive');
    expect(variantKindOf('anc-recent_deploy')).toBe('anchor_loss');
    expect(variantKindOf('neu-1')).toBe('neutral');
    expect(variantKindOf('auth-wrong-capacity')).toBe('authority');
    expect(variantKindOf('base')).toBe('base');
  });
  it('finding spans point at the stated surface in every variant', () => {
    for (const v of Object.values(inc.variants)) {
      for (const [fid, spans] of Object.entries(v.finding_spans ?? {})) {
        for (const s of spans) {
          expect(v.reports[s.report].slice(s.start, s.end)).toBe(s.surface);
          expect(v.truth_after[fid]).toBe(s.polarity);
        }
      }
    }
  });
  it('diff spans point at the before/after text', () => {
    let ops = 0;
    for (const v of Object.values(inc.variants)) {
      for (const [report, list] of Object.entries(v.diff)) {
        for (const op of list ?? []) {
          ops++;
          expect(inc.variants.base.reports[report].slice(op.base_span[0], op.base_span[1])).toBe(op.before);
          expect(v.reports[report].slice(op.variant_span[0], op.variant_span[1])).toBe(op.after);
        }
      }
    }
    expect(ops).toBeGreaterThan(4);
    expect(inc.variants['auth-wrong-capacity'].diff.alerts?.[0].op).toBe('insert');
  });
});
