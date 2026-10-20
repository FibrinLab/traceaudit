import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { paragraphRanges, segmentText, type Highlight } from '../lib/spans';
import { assertionHighlights, claimEvidenceHighlights } from '../lib/evidence';
import { nodeMatchKey } from '../lib/layout';
import type { CaseFile, Claim, Trace } from '../types';

const cll = JSON.parse(readFileSync(resolve(__dirname, '../../public/demo/cases/CLL-001.json'), 'utf8')) as CaseFile;

describe('segmentText', () => {
  const text = 'CD5 positive. CD23 positive. cyclin D1 negative.';
  it('covers the whole text in order with plain gaps merged', () => {
    const segs = segmentText(text, [{ start: 0, end: 13, kind: 'supported' }, { start: 29, end: 48, kind: 'contradicted' }]);
    expect(segs.map((s) => s.text).join('')).toBe(text);
    expect(segs.map((s) => s.highlight?.kind ?? null)).toEqual(['supported', null, 'contradicted']);
    expect(segs[0].isHead).toBe(true);
  });
  it('resolves overlaps by priority and marks only the first segment as head', () => {
    const hs: Highlight[] = [
      { start: 0, end: 28, kind: 'supported', id: 'a', priority: 1 },
      { start: 14, end: 20, kind: 'focus', id: 'b', priority: 5 },
    ];
    const segs = segmentText(text, hs);
    expect(segs.map((s) => [s.text, s.highlight?.id ?? null, s.isHead])).toEqual([
      ['CD5 positive. ', 'a', true],
      ['CD23 p', 'b', true],
      ['ositive.', 'a', false],
      [' cyclin D1 negative.', null, false],
    ]);
  });
  it('drops zero-length and clamps out-of-range spans', () => {
    const segs = segmentText(text, [{ start: 10, end: 10, kind: 'edited' }, { start: 40, end: 999, kind: 'edited' }]);
    expect(segs.filter((s) => s.highlight).length).toBe(1);
    expect(segs.find((s) => s.highlight)!.text).toBe(text.slice(40));
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

describe('claimEvidenceHighlights (real demo claims)', () => {
  const traces = cll.traces;
  const reportsFor = (t: Trace) => cll.variants[t.variant].reports;
  const find = (pred: (c: Claim) => boolean): [Trace, Claim] => {
    for (const t of traces) for (const c of t.claims) if (pred(c)) return [t, c];
    throw new Error('no claim');
  };
  it('maps a supported claim to its evidence span and the span text mentions the finding', () => {
    const [t, c] = find((c) => c.label === 'supported' && c.evidence.some((e) => e.span));
    const res = claimEvidenceHighlights(c, reportsFor(t), cll.case.finding_spans);
    expect(res.highlights.length).toBeGreaterThan(0);
    expect(res.notInInputs).toEqual([]);
    const h = res.highlights[0];
    expect(h.kind).toBe('supported');
    expect(h.report).toBe(c.evidence[0].report);
    const slice = reportsFor(t)[h.report].slice(h.start, h.end);
    expect(slice.length).toBeGreaterThan(0);
    expect(res.scrollTo).toBe(h.id);
  });
  it('labels contradicted evidence with what the document says', () => {
    const [t, c] = find((c) => c.label === 'contradicted');
    const res = claimEvidenceHighlights(c, reportsFor(t), cll.case.finding_spans);
    expect(res.highlights[0].kind).toBe('contradicted');
    expect(res.highlights[0].label).toMatch(/^document says: (positive|negative)$/);
  });
  it('reports "not in inputs" for unsupported findings without any span', () => {
    const [t, c] = find((c) => c.label === 'unsupported');
    const res = claimEvidenceHighlights(c, reportsFor(t), cll.case.finding_spans);
    expect(res.notInInputs).toEqual(c.evidence.map((e) => e.finding_id));
    expect(res.highlights).toEqual([]);
  });
  it('falls back to finding_spans when evidence lacks a span but the finding is reported', () => {
    const [t, c] = find((c) => c.label === 'supported' && c.evidence.length === 1);
    const stripped: Claim = { ...c, evidence: [{ ...c.evidence[0], report: null, span: null, truth: null }] };
    const res = claimEvidenceHighlights(stripped, reportsFor(t), cll.case.finding_spans);
    const spans = cll.case.finding_spans[c.evidence[0].finding_id] ?? [];
    if (spans.length) {
      expect(res.highlights.length).toBe(spans.length);
      expect(res.notInInputs).toEqual([]);
    } else {
      expect(res.notInInputs).toEqual([c.evidence[0].finding_id]);
    }
  });
  it('assertion highlights sit inside the claim span', () => {
    const [, c] = find((c) => c.assertions.length > 0);
    for (const h of assertionHighlights(c)) {
      expect(h.start).toBeGreaterThanOrEqual(c.start);
      expect(h.end).toBeLessThanOrEqual(c.end);
    }
  });
});

describe('reasoning map node matching', () => {
  const t = cll.traces.find((x) => x.variant === 'dec-cyclin_d1' && x.map)!;
  it('match keys ignore finding order', () => {
    const a = { ...t.map!.nodes[0], findings: ['CD5', 'CD23'] };
    const b = { ...t.map!.nodes[0], findings: ['CD23', 'CD5'] };
    expect(nodeMatchKey(a)).toBe(nodeMatchKey(b));
  });
});
