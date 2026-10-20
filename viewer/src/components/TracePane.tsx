import { useCallback, useEffect, useMemo, useRef, type KeyboardEvent } from 'react';
import type { Claim, ClaimType } from '../types';
import { paragraphRanges, segmentText, type Highlight } from '../lib/spans';
import { claimKind, labelIcon } from '../lib/format';
import { prefersReducedMotion } from './ReportPane';

interface Props {
  reasoning: string;
  claims?: Claim[];
  selectedClaimId?: number | null;
  onSelectClaim?: (claim: Claim) => void;
  /** Extra non-claim highlights (primary mention, ack span, …). */
  extraHighlights?: Highlight[];
  /** Claim types to show as coloured spans; others are rendered plain. */
  visibleTypes?: Set<ClaimType>;
  onlyProblems?: boolean;
  /** When true, no claim colouring at all (rating mode). */
  plain?: boolean;
  scrollToHighlightId?: string | null;
  title?: string;
  ariaLabel?: string;
  /** Reports which claims are currently scrolled into view (for the sequential strip). */
  onVisibleClaims?: (ids: Set<number>) => void;
}

export function TracePane({ reasoning, claims = [], selectedClaimId = null, onSelectClaim, extraHighlights = [], visibleTypes, onlyProblems = false, plain = false, scrollToHighlightId, title, ariaLabel, onVisibleClaims }: Props) {
  const root = useRef<HTMLDivElement>(null);
  const paragraphs = useMemo(() => paragraphRanges(reasoning), [reasoning]);

  const claimById = useMemo(() => new Map(claims.map((c) => [c.claim_id, c])), [claims]);
  const highlights: Highlight[] = useMemo(() => {
    if (plain) return extraHighlights;
    const hs: Highlight[] = claims
      .filter((c) => !visibleTypes || visibleTypes.has(c.type))
      .map((c) => ({ start: c.start, end: c.end, kind: claimKind(c.type, c.label), id: `claim-${c.claim_id}`, priority: 1,
        title: c.type === 'knowledge' && c.knowledge_check ? `Knowledge check: ${c.knowledge_check.verdict}${c.knowledge_check.evidence ? ` (${c.knowledge_check.evidence})` : ''}` : undefined }));
    return [...hs, ...extraHighlights.map((h) => ({ ...h, priority: h.priority ?? 2 }))];
  }, [claims, extraHighlights, visibleTypes, plain]);

  useEffect(() => {
    if (!scrollToHighlightId || !root.current) return;
    const el = root.current.querySelector<HTMLElement>(`[data-hl-id="${scrollToHighlightId}"]`);
    if (el) el.scrollIntoView({ block: 'center', behavior: prefersReducedMotion() ? 'auto' : 'smooth' });
  }, [scrollToHighlightId]);

  useEffect(() => {
    const el = root.current;
    if (!el || !onVisibleClaims) return;
    let raf = 0;
    const compute = () => {
      const r = el.getBoundingClientRect();
      const ids = new Set<number>();
      el.querySelectorAll<HTMLElement>('.claim[data-claim-id]').forEach((c) => {
        const b = c.getBoundingClientRect();
        if (b.bottom >= r.top && b.top <= r.bottom) ids.add(Number(c.dataset.claimId));
      });
      onVisibleClaims(ids);
    };
    const onScroll = () => { cancelAnimationFrame(raf); raf = requestAnimationFrame(compute); };
    compute();
    el.addEventListener('scroll', onScroll, { passive: true });
    return () => { el.removeEventListener('scroll', onScroll); cancelAnimationFrame(raf); };
  }, [onVisibleClaims, claims, reasoning]);

  const focusables = useCallback(() => Array.from(root.current?.querySelectorAll<HTMLElement>('.claim[tabindex="0"]') ?? []), []);

  const onKey = (e: KeyboardEvent<HTMLElement>, claim: Claim) => {
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSelectClaim?.(claim); return; }
    if (e.key === 'ArrowDown' || e.key === 'ArrowRight' || e.key === 'ArrowUp' || e.key === 'ArrowLeft') {
      e.preventDefault();
      const list = focusables();
      const i = list.indexOf(e.currentTarget);
      const next = e.key === 'ArrowDown' || e.key === 'ArrowRight' ? list[Math.min(list.length - 1, i + 1)] : list[Math.max(0, i - 1)];
      next?.focus();
    }
  };

  const isProblem = (c: Claim) => c.label === 'contradicted' || c.label === 'unsupported' || (c.knowledge_check?.verdict === 'inconsistent');

  return (
    <div className="pane trace-pane" ref={root} role="region" aria-label={ariaLabel ?? title ?? 'Reasoning trace'}>
      {title && <div className="pane-title">{title}</div>}
      <div className="trace-text">
        {paragraphs.map(([ps, pe], pi) => {
          const text = reasoning.slice(ps, pe);
          const local = highlights.filter((h) => h.end > ps && h.start < pe).map((h) => ({ ...h, start: Math.max(h.start, ps) - ps, end: Math.min(h.end, pe) - ps }));
          const segs = segmentText(text, local);
          return (
            <p key={pi}>
              {segs.map((s, i) => {
                if (!s.highlight) return <span key={i}>{s.text}</span>;
                const h = s.highlight;
                const m = /^claim-(\d+)$/.exec(h.id ?? '');
                if (m) {
                  const claim = claimById.get(Number(m[1]));
                  if (!claim) return <span key={i}>{s.text}</span>;
                  const dim = onlyProblems && !isProblem(claim);
                  const selected = selectedClaimId === claim.claim_id;
                  const kind = claimKind(claim.type, claim.label);
                  const labelText = claim.type === 'factual' ? (claim.label ?? 'unlabelled') : claim.type;
                  return (
                    <span
                      key={i}
                      className={`claim claim-${kind}${dim ? ' dimmed' : ''}`}
                      role="button"
                      tabIndex={s.isHead ? 0 : -1}
                      aria-pressed={selected}
                      aria-label={`${labelText} ${claim.type} claim ${claim.claim_id}: ${claim.text}`}
                      data-hl-id={s.isHead ? h.id : undefined}
                      data-claim-id={claim.claim_id}
                      title={h.title ?? `${labelText} ${claim.type}`}
                      onClick={() => onSelectClaim?.(claim)}
                      onKeyDown={(e) => onKey(e, claim)}
                    >
                      {s.isHead && kind !== 'other' && <span className="hl-icon" aria-hidden="true">{labelIcon(kind)}</span>}
                      {s.text}
                      {s.isHead && kind !== 'other' && <span className="hl-label" aria-hidden="true">{labelText}</span>}
                    </span>
                  );
                }
                return (
                  <mark key={i} className={`hl hl-${h.kind}`} data-hl-id={s.isHead ? h.id : undefined} title={h.title}>
                    {s.isHead && <span className="hl-icon" aria-hidden="true">{labelIcon(h.kind)}</span>}
                    {s.text}
                    {s.isHead && h.label && <span className="hl-label">{h.label}</span>}
                  </mark>
                );
              })}
            </p>
          );
        })}
        {!reasoning && <p className="muted">(empty reasoning)</p>}
      </div>
    </div>
  );
}
