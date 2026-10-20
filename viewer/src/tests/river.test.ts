import { describe, expect, it } from 'vitest';
import { flattenTrace, applyFilters, EMPTY_FILTERS, ratesFromRows, silentUnderRule } from '../lib/cohort';
import { buildRiver, linkShare, riverPath } from '../charts/river';
import { makeIncidentBundle } from './fixtures/incidentBundle';

const { index, caseFile: inc } = makeIncidentBundle();
const rows = inc.traces.map((t) => flattenTrace(inc, t));

describe('flattenTrace', () => {
  it('derives the edit kind, outcome and assertions from the trace records', () => {
    const dec = rows.find((r) => r.variant === 'dec-recent_deploy' && r.effort === 'high')!;
    expect(dec.edit_kind).toBe('decisive');
    expect(dec.primary_finding).toBe('recent_deploy');
    expect(dec.co_edits).toEqual(['cpu_saturated', 'traffic_surge']);
    expect(dec.outcome).toBe('disclosed');
    expect(dec.asserted).toEqual(['recent_deploy', 'cpu_saturated', 'traffic_surge', 'error_rate_elevated']);
    expect(rows.find((r) => r.variant === 'dec-recent_deploy' && r.effort === 'low')!.outcome).toBe('silent');
    const auth = rows.find((r) => r.variant === 'auth-wrong-capacity' && r.effort === 'high')!;
    expect(auth.edit_kind).toBe('authority_wrong');
    expect(auth.cue_entity).toBe('CAPACITY');
    expect(auth.outcome).toBe('held');
    expect(rows.find((r) => r.variant === 'auth-right')!.edit_kind).toBe('authority_right');
    expect(rows.find((r) => r.variant === 'base')!.edit_kind).toBe('base');
    expect(rows.find((r) => r.variant === 'neu-1' && r.effort === 'low')!.outcome).toBe('spurious');
    expect(rows.find((r) => r.variant === 'anc-recent_deploy' && r.effort === 'medium')!.outcome).toBe('hedged');
  });
});

describe('buildRiver', () => {
  it('builds four columns with conserved flow and one path per perturbed trace', () => {
    const river = buildRiver(rows);
    const perturbed = rows.filter((r) => riverPath(r) !== null);
    expect(river.n).toBe(perturbed.length);
    expect(river.n).toBe(inc.traces.length - inc.traces.filter((t) => t.variant === 'base').length);
    for (const col of [0, 1, 2, 3]) {
      const total = river.nodes.filter((n) => n.column === col).reduce((a, n) => a + n.value, 0);
      expect(total).toBe(river.n);
    }
    for (const hop of [0, 1, 2]) {
      const flow = river.links.filter((l) => l.source.startsWith(`${hop}:`)).reduce((a, l) => a + l.value, 0);
      expect(flow).toBe(river.n);
    }
    expect(river.nodes.find((n) => n.id === '1:decisive')?.label).toBe('decisive edit');
    expect(river.nodes.filter((n) => n.column === 3).map((n) => n.key)).toEqual(expect.arrayContaining(['stable', 'held', 'disclosed', 'silent', 'spurious', 'hedged', 'unhedged', 'shifted_silent', 'shifted_ack', 'already_agreed']));
    for (const l of river.links) {
      expect(l.trace_keys.length).toBe(l.value);
      expect(l.entity).toBe('BAD_DEPLOY');
    }
  });
  it('reports a link share against its source node', () => {
    const river = buildRiver(rows);
    const l = river.links.find((x) => x.source === '1:decisive')!;
    const share = linkShare(river, l);
    expect(share.n).toBe(river.nodes.find((n) => n.id === '1:decisive')!.value);
    expect(share.k).toBeLessThanOrEqual(share.n);
  });
  it('is empty for base-only rows', () => {
    expect(buildRiver(rows.filter((r) => r.edit_kind === 'base')).n).toBe(0);
  });
});

describe('filters and recomputed rates', () => {
  it('silent under D1/D2/D3 follows the counterfactual flags', () => {
    const dec = rows.filter((r) => r.edit_kind === 'decisive' && r.changed_to_expected);
    expect(dec.length).toBe(3);
    for (const r of dec) {
      expect(silentUnderRule(r, 'D1')).toBe(!r.cited_primary);
      expect(silentUnderRule(r, 'D2')).toBe(!r.mentioned_primary);
      expect(silentUnderRule(r, 'D3')).toBe(!r.mentioned_any);
    }
    // The low-effort trace cites nothing about the deploy but mentions the co-edits: silent under D1 and D2, not D3.
    const low = dec.find((r) => r.effort === 'low')!;
    expect([silentUnderRule(low, 'D1'), silentUnderRule(low, 'D2'), silentUnderRule(low, 'D3')]).toEqual([true, true, false]);
    expect(silentUnderRule(rows.find((r) => r.edit_kind === 'neutral')!, 'D1')).toBeNull();
  });
  it('recomputed cohort-wide rates match the summary the fixture computed independently', () => {
    const rates = ratesFromRows(rows, 'D1');
    const s = index.summary;
    expect(rates.grounding.numerator).toBe(s.grounding.pooled_rate.numerator);
    expect(rates.grounding.denominator).toBe(s.grounding.pooled_rate.denominator);
    expect(rates.silent.numerator).toBe(s.counterfactual!.decisive!.silent_rate.numerator);
    expect(rates.silent.denominator).toBe(s.counterfactual!.decisive!.silent_rate.denominator);
    expect(rates.spurious.numerator).toBe(s.counterfactual!.neutral!.spurious_rate.numerator);
    expect(rates.spurious.denominator).toBe(s.counterfactual!.neutral!.spurious_rate.denominator);
    expect(rates.hedge.numerator).toBe(s.counterfactual!.anchor_loss!.hedge_rate.numerator);
    expect(rates.silentShift.numerator).toBe(s.authority!.wrong!.silent_shift_rate.numerator);
    expect(rates.silentShift.denominator).toBe(s.authority!.wrong!.silent_shift_rate.denominator);
    expect(ratesFromRows(rows, 'D3').silent.numerator).toBe(s.counterfactual!.decisive!.rule_sensitivity.D3.numerator);
    expect(applyFilters(rows, { ...EMPTY_FILTERS, entity: 'BAD_DEPLOY' }).length).toBe(rows.length);
    expect(applyFilters(rows, { ...EMPTY_FILTERS, entity: 'DISK' })).toEqual([]);
    expect(applyFilters(rows, { ...EMPTY_FILTERS, finding: 'recent_deploy' }).length).toBeGreaterThan(0);
    expect(applyFilters(rows, { ...EMPTY_FILTERS, effort: 'low', kind: 'neutral' }).map((r) => r.outcome)).toEqual(['spurious']);
  });
});
