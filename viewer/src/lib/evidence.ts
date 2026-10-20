import type { Claim, FindingSpan, ReportName, Reports } from '../types';
import type { ReportHighlight } from '../components/ReportPane';
import { polarityText } from './format';

export interface ClaimEvidenceResult {
  highlights: ReportHighlight[];
  /** Findings the claim asserted that are not in any document. */
  notInInputs: string[];
  /** The first highlight id, for scrolling. */
  scrollTo: string | null;
}

/**
 * Build report highlights for a selected claim: use `evidence[].report/span` when present,
 * fall back to `finding_spans[finding_id]` when the span text still matches the report text
 * (finding_spans are offsets into the base reports, so a perturbed variant may have shifted).
 */
export function claimEvidenceHighlights(
  claim: Claim,
  reports: Reports,
  findingSpans: Record<string, FindingSpan[]> | undefined,
  displayFinding: (id: string) => string = (id) => id,
): ClaimEvidenceResult {
  const highlights: ReportHighlight[] = [];
  const notInInputs: string[] = [];
  const kind = claim.label === 'contradicted' ? 'contradicted' : claim.label === 'supported' ? 'supported' : 'unsupported';
  let i = 0;
  const seenFindings = new Set<string>();

  for (const ev of claim.evidence) {
    seenFindings.add(ev.finding_id);
    if (ev.report && ev.span && ev.span[1] > ev.span[0]) {
      const label = ev.truth === null
        ? 'not in inputs'
        : claim.label === 'contradicted' && ev.truth !== ev.claimed
          ? `document says: ${polarityText(ev.truth)}`
          : `document: ${displayFinding(ev.finding_id)} ${polarityText(ev.truth)}`;
      highlights.push({ report: ev.report, start: ev.span[0], end: ev.span[1], kind, label, id: `ev-${claim.claim_id}-${i++}`, priority: 3 });
      continue;
    }
    if (ev.truth === null || !ev.report) {
      // Try finding_spans as a fallback before declaring it absent.
      const fb = fallbackSpans(ev.finding_id, reports, findingSpans);
      if (fb.length) {
        for (const s of fb) highlights.push({ ...s, kind, label: `document: ${displayFinding(ev.finding_id)} ${polarityText(s.polarity)}`, id: `ev-${claim.claim_id}-${i++}`, priority: 3 });
      } else {
        notInInputs.push(ev.finding_id);
      }
    }
  }
  // Assertions with no evidence record at all (e.g. knowledge/other claims): try finding_spans.
  for (const a of claim.assertions) {
    if (seenFindings.has(a.finding_id)) continue;
    seenFindings.add(a.finding_id);
    const fb = fallbackSpans(a.finding_id, reports, findingSpans);
    for (const s of fb) highlights.push({ ...s, kind: 'mention', label: `${displayFinding(a.finding_id)} ${polarityText(s.polarity)}`, id: `ev-${claim.claim_id}-${i++}`, priority: 2 });
  }
  return { highlights, notInInputs, scrollTo: highlights[0]?.id ?? null };
}

function fallbackSpans(findingId: string, reports: Reports, findingSpans: Record<string, FindingSpan[]> | undefined): Array<{ report: ReportName; start: number; end: number; polarity: 'pos' | 'neg' }> {
  const spans = findingSpans?.[findingId] ?? [];
  const out: Array<{ report: ReportName; start: number; end: number; polarity: 'pos' | 'neg' }> = [];
  for (const s of spans) {
    const text = reports[s.report] ?? '';
    const slice = text.slice(s.start, s.end);
    if (s.surface && slice !== s.surface) {
      // Shifted by an edit: search for the surface text instead.
      const at = text.indexOf(s.surface);
      if (at >= 0) out.push({ report: s.report, start: at, end: at + s.surface.length, polarity: s.polarity });
      continue;
    }
    if (slice) out.push({ report: s.report, start: s.start, end: s.end, polarity: s.polarity });
  }
  return out;
}

/** Highlights for the claim's own assertion spans inside the trace (absolute offsets into reasoning). */
export function assertionHighlights(claim: Claim) {
  return claim.assertions
    .filter((a) => a.end > a.start)
    .map((a, i) => ({ start: a.start, end: a.end, kind: 'focus' as const, id: `assert-${claim.claim_id}-${i}`, priority: 5, title: `asserts ${a.finding_id} ${a.polarity ?? ''}`.trim() }));
}
