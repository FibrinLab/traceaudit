import { useEffect, useRef, type ReactNode } from 'react';
import type { ReportName, Reports, Section } from '../types';
import { sectionsFor } from '../lib/documents';
import { segmentText, type Highlight } from '../lib/spans';
import { labelIcon } from '../lib/format';

export interface ReportHighlight extends Highlight { report: ReportName }

interface Props {
  /** Section id → document text. */
  reports: Reports;
  /** Declared sections (from the case or the analysis); derived from the keys when absent. */
  sections?: Section[] | null;
  highlights?: ReportHighlight[];
  /** id of the highlight to scroll into view */
  scrollTo?: string | null;
  title?: string;
  /** Extra content rendered under a given section (e.g. the "Edited: …" line). */
  footers?: Partial<Record<string, ReactNode>>;
  emptyText?: string;
  /** When given, highlights with an id are clickable (and reachable by keyboard) and report that id. */
  onHighlightClick?: (id: string) => void;
}

/** The source documents of a case, one section per heading, with inline highlights. */
export function ReportPane({ reports, sections, highlights = [], scrollTo, title, footers, emptyText = 'Not provided.', onHighlightClick }: Props) {
  const root = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!scrollTo || !root.current) return;
    const el = root.current.querySelector<HTMLElement>(`[data-hl-id="${cssEscape(scrollTo)}"]`);
    if (el) el.scrollIntoView({ block: 'center', behavior: prefersReducedMotion() ? 'auto' : 'smooth' });
  }, [scrollTo]);
  const secs = sectionsFor(reports, sections);

  return (
    <div className="pane report-pane" ref={root} aria-label={title ?? 'Source documents'} role="region">
      {title && <div className="pane-title">{title}</div>}
      {secs.map(({ id, title: heading }) => {
        const text = reports[id] ?? '';
        const hs = highlights.filter((h) => h.report === id);
        return (
          <section key={id} aria-labelledby={`rp-${id}`}>
            <h3 id={`rp-${id}`}>{heading}</h3>
            <div className="report-text">
              {text ? <HighlightedText text={text} highlights={hs} onClick={onHighlightClick} /> : <span className="muted">{emptyText}</span>}
            </div>
            {footers?.[id]}
          </section>
        );
      })}
    </div>
  );
}

export function HighlightedText({ text, highlights, onClick }: { text: string; highlights: Highlight[]; onClick?: (id: string) => void }) {
  const segs = segmentText(text, highlights);
  return (
    <>
      {segs.map((s, i) => {
        if (!s.highlight) return <span key={i}>{s.text}</span>;
        const h = s.highlight;
        const cls = `hl hl-${h.kind}${onClick && h.id ? ' hl-click' : ''}`;
        const click = onClick && h.id ? () => onClick(h.id!) : undefined;
        return (
          <mark key={i} className={cls} data-hl-id={s.isHead ? h.id : undefined} title={h.title}
            role={click ? 'button' : undefined} tabIndex={click && s.isHead ? 0 : undefined} onClick={click}
            onKeyDown={click ? (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); click(); } } : undefined}>
            {s.isHead && <span className="hl-icon" aria-hidden="true">{labelIcon(h.kind)}</span>}
            {s.text}
            {s.isHead && h.label && <span className="hl-label">{h.label}</span>}
            {s.isHead && !h.label && <span className="visually-hidden">{h.kind}</span>}
          </mark>
        );
      })}
    </>
  );
}

export function prefersReducedMotion(): boolean {
  return typeof window !== 'undefined' && !!window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

function cssEscape(s: string): string {
  return typeof CSS !== 'undefined' && CSS.escape ? CSS.escape(s) : s.replace(/["\\]/g, '\\$&');
}
