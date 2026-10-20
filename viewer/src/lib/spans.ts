// Helpers for turning (start, end) highlights into renderable segments.

export type HighlightKind = 'supported' | 'contradicted' | 'unsupported' | 'inferential' | 'knowledge' | 'edited' | 'cue' | 'mention' | 'ack' | 'other' | 'focus';

export interface Highlight {
  start: number;
  end: number;
  kind: HighlightKind;
  /** Short visible text label (e.g. "supported", "edited"). */
  label?: string;
  /** Stable id, used for scroll-to and click handling. */
  id?: string;
  /** Extra title shown on hover. */
  title?: string;
  /** Higher priority wins when spans overlap. */
  priority?: number;
}

export interface Segment {
  start: number;
  end: number;
  text: string;
  /** The highlight covering this segment, or null for plain text. */
  highlight: Highlight | null;
  /** True for the first segment of a highlight (where the label/icon is drawn). */
  isHead: boolean;
}

export function clampSpan(start: number, end: number, length: number): [number, number] {
  const s = Math.max(0, Math.min(length, Math.floor(start)));
  const e = Math.max(s, Math.min(length, Math.floor(end)));
  return [s, e];
}

/**
 * Split `text` into contiguous segments so that each segment belongs to at most one
 * highlight. Overlaps are resolved by priority (then by earlier start). Zero-length
 * spans are dropped. Output covers the whole text, in order.
 */
export function segmentText(text: string, highlights: readonly Highlight[]): Segment[] {
  const n = text.length;
  const hs = highlights
    .map((h) => { const [s, e] = clampSpan(h.start, h.end, n); return { ...h, start: s, end: e }; })
    .filter((h) => h.end > h.start)
    .sort((a, b) => (b.priority ?? 0) - (a.priority ?? 0) || a.start - b.start);
  if (hs.length === 0) return n ? [{ start: 0, end: n, text, highlight: null, isHead: false }] : [];

  // Boundaries at every span edge.
  const cuts = new Set<number>([0, n]);
  for (const h of hs) { cuts.add(h.start); cuts.add(h.end); }
  const points = [...cuts].sort((a, b) => a - b);

  const segs: Segment[] = [];
  const seen = new Set<Highlight>();
  for (let i = 0; i < points.length - 1; i++) {
    const s = points[i], e = points[i + 1];
    if (e <= s) continue;
    const owner = hs.find((h) => h.start <= s && h.end >= e) ?? null;
    const isHead = owner ? !seen.has(owner) : false;
    if (owner) seen.add(owner);
    // Merge consecutive plain segments.
    const prev = segs[segs.length - 1];
    if (!owner && prev && !prev.highlight) {
      prev.end = e; prev.text = text.slice(prev.start, e);
    } else if (owner && prev && prev.highlight === owner) {
      prev.end = e; prev.text = text.slice(prev.start, e);
    } else {
      segs.push({ start: s, end: e, text: text.slice(s, e), highlight: owner, isHead });
    }
  }
  return segs;
}

/** Split text into paragraphs by blank lines, returning [start, end) offsets. */
export function paragraphRanges(text: string): Array<[number, number]> {
  const out: Array<[number, number]> = [];
  const re = /\n\s*\n/g;
  let last = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text))) {
    out.push([last, m.index]);
    last = m.index + m[0].length;
  }
  out.push([last, text.length]);
  return out.filter(([s, e]) => e > s);
}
