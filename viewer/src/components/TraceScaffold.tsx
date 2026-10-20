import { useCallback, useRef, useState, type KeyboardEvent, type ReactNode } from 'react';
import type { CaseFile, Trace } from '../types';
import { variantKindOf } from '../types';
import { hrefCase, hrefTrace } from '../lib/router';
import { useStore } from '../store';
import { TraceHeader } from './Shared';

/** Header shared by the per-trace views: breadcrumbs, identity chips, view tabs. */
export function TraceScaffold({ trace, caseFile, active, children }: { trace: Trace; caseFile: CaseFile; active: 'grounding' | 'counterfactual' | 'authority' | 'map'; children: ReactNode }) {
  const { bundle } = useStore();
  const kind = variantKindOf(trace.variant);
  const tabs: Array<['grounding' | 'counterfactual' | 'authority' | 'map', string, boolean]> = [
    ['grounding', 'Grounding', true],
    ['counterfactual', 'Counterfactual diff', kind === 'decisive' || kind === 'anchor_loss' || kind === 'neutral'],
    ['authority', 'Authority', kind === 'authority'],
    ['map', 'Constellation', !!trace.map],
  ];
  return (
    <div>
      <nav aria-label="Breadcrumb" className="crumbs">
        <a href="#/cases">Cases</a><span className="sep">/</span><a href={hrefCase(caseFile.case.case_id)}>{caseFile.case.case_id}</a><span className="sep">/</span><span className="mono">{trace.trace_key}</span>
      </nav>
      <TraceHeader trace={trace} caseId={caseFile.case.case_id} entity={caseFile.case.entity} lexicon={bundle?.index.lexicon} modelTag={String(bundle?.index.run.manifest.model?.tag ?? '')} runId={bundle?.index.run.run_id} />
      <nav aria-label="Trace views" className="view-tabs">
        {tabs.filter(([, , ok]) => ok).map(([view, label]) => (
          <a key={view} href={hrefTrace(trace.trace_key, view)} aria-current={active === view ? 'page' : undefined}>{label}</a>
        ))}
      </nav>
      {children}
    </div>
  );
}

/** Two-column resizable split (keyboard: ← → on the gutter). Stacks under 900 px via CSS. */
export function Split({ left, right, initial = 45 }: { left: ReactNode; right: ReactNode; initial?: number }) {
  const [pctLeft, setPctLeft] = useState(initial);
  const ref = useRef<HTMLDivElement>(null);
  const dragging = useRef(false);

  const onPointerDown = useCallback(() => { dragging.current = true; }, []);
  const onPointerMove = useCallback((e: React.PointerEvent) => {
    if (!dragging.current || !ref.current) return;
    const r = ref.current.getBoundingClientRect();
    setPctLeft(Math.max(20, Math.min(80, ((e.clientX - r.left) / r.width) * 100)));
  }, []);
  const stop = useCallback(() => { dragging.current = false; }, []);
  const onKey = (e: KeyboardEvent) => {
    if (e.key === 'ArrowLeft') setPctLeft((p) => Math.max(20, p - 5));
    if (e.key === 'ArrowRight') setPctLeft((p) => Math.min(80, p + 5));
  };
  return (
    <div className="split" ref={ref} style={{ ['--split-left' as string]: `${pctLeft}%` }} onPointerMove={onPointerMove} onPointerUp={stop} onPointerLeave={stop}>
      <div style={{ minWidth: 0 }}>{left}</div>
      <button type="button" className="gutter" aria-label="Resize panes (use left and right arrow keys)" onPointerDown={onPointerDown} onKeyDown={onKey} />
      <div style={{ minWidth: 0 }}>{right}</div>
    </div>
  );
}

export function baseTracesFor(caseFile: CaseFile, effort: string): Trace[] {
  return caseFile.traces.filter((t) => t.variant === 'base' && t.effort === effort).sort((a, b) => a.run - b.run);
}
