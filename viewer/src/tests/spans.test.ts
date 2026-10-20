import { describe, expect, it } from 'vitest';
import { paragraphRanges, segmentText, type Highlight } from '../lib/spans';
import { assertionHighlights, claimEvidenceHighlights } from '../lib/evidence';
import { nodeMatchKey } from '../lib/layout';
import type { Claim, Trace } from '../types';
import { makeIncidentBundle } from './fixtures/incidentBundle';

const { caseFile: inc } = makeIncidentBundle();

describe('segmentText', () => {
  const text = 'Error rate elevated. CPU normal. Disk full.';
  it('covers the whole text in order with plain gaps merged', () => {
    const segs = segmentText(text, [{ start: 0, end: 20, kind: 'supported' }, { start: 33, end: 43, kind: 'contradicted' }]);
    expect(segs.map((s) => s.text).join('')).toBe(text);
    expect(segs.map((s) => s.highlight?.kind ?? null)).toEqual(['supported', null, 'contradicted']);
    expect(segs[0].isHead).toBe(true);
  });
  it('resolves overlaps by priority and marks only the first segment as head', () => {
    const hs: Highlight[] = [
      { start: 0, end: 32, kind: 'supported', id: 'a', priority: 1 },
      { start: 21, end: 24, kind: 'focus', id: 'b', priority: 5 },
    ];
    const segs = segmentText(text, hs);
    expect(segs.map((s) => [s.text, s.highlight?.id ?? null, s.isHead])).toEqual([
      ['Error rate elevated. ', 'a', true],
      ['CPU', 'b', true],
      [' normal.', 'a', false],
      [' Disk full.', null, false],
    ]);
  });
  it('drops zero-length and clamps out-of-range spans', () => {
    const segs = segmentText(text, [{ start: 10, end: 10, kind: 'edited' }, { start: 33, end: 999, kind: 'edited' }]);
    expect(segs.filter((s) => s.highlight).length).toBe(1);
    expect(segs.find((s) => s.highlight)!.text).toBe(text.slice(33));
  });
  it('returns one plain segment when nothing is highlighted', () => {
    expect(segmentText('abc', [])).toEqual([{ start: 0, end: 3, text: 'abc', highlight: null, isHead: false }]);
    expect(segmentText('', [])).toEqual([]);
  });
});

describe('paragraphRanges', () => {
  it('splits on blank lines and preserves offsets', () => {
    const t = 'one\n\ntwo\n  \nthree';
    const r = paragraphRanges(t);
    expect(r.map(([s, e]) => t.slice(s, e))).toEqual(['one', 'two', 'three']);
  });
});

describe('claimEvidenceHighlights (synthetic claims)', () => {
  const traces = inc.traces;
  const reportsFor = (t: Trace) => inc.variants[t.variant].reports;
  const find = (pred: (c: Claim) => boolean): [Trace, Claim] => {
    for (const t of traces) for (const c of t.claims) if (pred(c)) return [t, c];
    throw new Error('no claim');
  };
  it('maps a supported claim to its evidence span and the span text mentions the finding', () => {
    const [t, c] = find((c) => c.label === 'supported' && c.evidence.some((e) => e.span));
    const res = claimEvidenceHighlights(c, reportsFor(t), inc.case.finding_spans);
    expect(res.highlights.length).toBeGreaterThan(0);
    expect(res.notInInputs).toEqual([]);
    const h = res.highlights[0];
    expect(h.kind).toBe('supported');
    expect(h.report).toBe(c.evidence[0].report);
    const slice = reportsFor(t)[h.report].slice(h.start, h.end);
    expect(slice).toBe('Error rate elevated');
    expect(h.label).toBe('document: error_rate_elevated positive');
    expect(res.scrollTo).toBe(h.id);
  });
  it('labels contradicted evidence with what the document says', () => {
    const [t, c] = find((c) => c.label === 'contradicted');
    const res = claimEvidenceHighlights(c, reportsFor(t), inc.case.finding_spans);
    expect(res.highlights[0].kind).toBe('contradicted');
    expect(res.highlights[0].label).toBe('document says: negative');
    expect(reportsFor(t)[res.highlights[0].report].slice(res.highlights[0].start, res.highlights[0].end)).toBe('CPU normal');
  });
  it('reports "not in inputs" for unsupported findings without any span', () => {
    const [t, c] = find((c) => c.label === 'unsupported');
    const res = claimEvidenceHighlights(c, reportsFor(t), inc.case.finding_spans);
    expect(res.notInInputs).toEqual(['disk_full']);
    expect(res.highlights).toEqual([]);
  });
  it('falls back to finding_spans when evidence lacks a span but the finding is stated', () => {
    const [t, c] = find((c) => c.label === 'supported' && c.evidence.length === 1);
    const stripped: Claim = { ...c, evidence: [{ ...c.evidence[0], report: null, span: null, truth: null }] };
    const res = claimEvidenceHighlights(stripped, reportsFor(t), inc.case.finding_spans);
    const spans = inc.case.finding_spans[c.evidence[0].finding_id] ?? [];
    expect(spans.length).toBe(1);
    expect(res.highlights.length).toBe(1);
    expect(res.notInInputs).toEqual([]);
  });
  it('searches for the surface text when an edit has shifted the base offsets', () => {
    // The wrong-cue variant prepends a sentence to the alerts, so base finding_spans no longer line up with its text.
    const t = traces.find((x) => x.variant === 'auth-wrong-capacity' && x.effort === 'high')!;
    const c = t.claims.find((x) => x.assertions.some((a) => a.finding_id === 'cpu_saturated'))!;
    const stripped: Claim = { ...c, evidence: c.evidence.map((e) => ({ ...e, report: null, span: null, truth: null })) };
    const res = claimEvidenceHighlights(stripped, reportsFor(t), inc.case.finding_spans);
    const cpu = res.highlights.find((h) => h.label?.startsWith('document: cpu_saturated'))!;
    expect(reportsFor(t).alerts.slice(cpu.start, cpu.end)).toBe('CPU normal');
  });
  it('assertion highlights sit inside the claim span', () => {
    const [, c] = find((c) => c.assertions.length > 1);
    const hs = assertionHighlights(c);
    expect(hs.length).toBe(c.assertions.length);
    for (const h of hs) {
      expect(h.start).toBeGreaterThanOrEqual(c.start);
      expect(h.end).toBeLessThanOrEqual(c.end);
    }
  });
});

describe('reasoning map node matching', () => {
  const t = inc.traces.find((x) => x.variant === 'dec-recent_deploy' && x.map)!;
  it('match keys ignore finding order', () => {
    const a = { ...t.map!.nodes[1], findings: ['cpu_saturated', 'traffic_surge'] };
    const b = { ...t.map!.nodes[1], findings: ['traffic_surge', 'cpu_saturated'] };
    expect(nodeMatchKey(a)).toBe(nodeMatchKey(b));
  });
});
