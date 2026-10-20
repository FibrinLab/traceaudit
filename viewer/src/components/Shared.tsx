import { useEffect, useRef, useState, type ReactNode } from 'react';
import type { Effort, GroundingRecord, Lexicon, Outcome, Trace } from '../types';
import { entityDisplay, OUTCOME_META, parseAnswer, KIND_TEXT } from '../lib/format';
import { variantKindOf } from '../types';
import { entityColor } from '../lib/palette';

export function Chip({ tone, icon, children, title, className = '' }: { tone?: string; icon?: string; children: ReactNode; title?: string; className?: string }) {
  return (
    <span className={`chip ${tone ?? ''} ${className}`} title={title}>
      {icon && <span className="icon" aria-hidden="true">{icon}</span>}
      {children}
    </span>
  );
}

export function OutcomeBadge({ outcome, large = false }: { outcome: Outcome | string | null | undefined; large?: boolean }) {
  if (!outcome) return <Chip tone="neutral">no outcome</Chip>;
  const m = OUTCOME_META[outcome as Outcome];
  if (!m) return <Chip tone="neutral">{outcome}</Chip>;
  return <Chip tone={m.tone} icon={m.icon} title={m.description} className={large ? 'badge-lg' : ''}>outcome: {m.text}</Chip>;
}

export function Banner({ tone = 'info', children, live = true }: { tone?: 'info' | 'warn' | 'bad' | 'good'; children: ReactNode; live?: boolean }) {
  return (
    <div className={`banner ${tone}`} role={tone === 'bad' || tone === 'warn' ? 'alert' : 'status'} aria-live={live ? 'polite' : undefined}>
      <span aria-hidden="true">{tone === 'bad' ? '✗' : tone === 'warn' ? '!' : tone === 'good' ? '✓' : 'ℹ'}</span>
      <div>{children}</div>
    </div>
  );
}

export function AnswerCard({ title, answer, lexicon, grounding, truthEntity, compact = false }: {
  title: string;
  answer: string;
  lexicon?: Lexicon;
  grounding?: GroundingRecord | null;
  /** The truth entity (hidden in rate mode by not passing it). */
  truthEntity?: string | null;
  compact?: boolean;
}) {
  const parsed = parseAnswer(answer);
  const entity = grounding?.answer_entity ?? null;
  const truthKnown = typeof truthEntity === 'string' && truthEntity !== '' && truthEntity !== 'UNKNOWN' && truthEntity !== 'OTHER';
  const correct = truthKnown ? (grounding?.answer_correct ?? (entity ? entity === truthEntity : null)) : null;
  return (
    <div className="answer-card">
      <div className="title">{title}</div>
      <div className="row" style={{ marginTop: 4 }}>
        {entity && <Chip tone="neutral" title={grounding?.answer_entity_raw ?? undefined}><span className="entity">Parsed: {entityDisplay(lexicon, entity)}</span></Chip>}
        {truthKnown && <Chip tone="neutral"><span className="entity">Truth: {entityDisplay(lexicon, truthEntity as string)}</span></Chip>}
        {grounding && (
          <>
            {grounding.answer_hedged
              ? <Chip tone="warn" icon="≈">hedged</Chip>
              : correct === true ? <Chip tone="good" icon="✓">correct</Chip>
              : correct === false ? <Chip tone="bad" icon="✗">incorrect</Chip>
              : null}
            {grounding.trace_answer_agree === false && <Chip tone="bad" icon="!">trace–answer mismatch</Chip>}
          </>
        )}
        {parsed.confidence && <Chip tone="neutral">confidence: {parsed.confidence}</Chip>}
      </div>
      {!compact && <pre className="answer-text" style={{ marginTop: 8 }}>{answer || '(empty answer)'}</pre>}
      {compact && parsed.label && <div style={{ marginTop: 6 }}>{parsed.label}</div>}
    </div>
  );
}

export function TraceHeader({ trace, caseId, entity, lexicon, modelTag, runId, blinded = false, presentation }: {
  trace: Trace;
  caseId: string;
  entity?: string;
  lexicon?: Lexicon;
  modelTag?: string;
  runId?: string;
  blinded?: boolean;
  presentation?: { index: number; total: number };
}) {
  if (blinded) {
    return (
      <div className="row small muted" aria-label="Trace identification (blinded)">
        {presentation && <strong style={{ color: 'var(--text)' }}>Trace {presentation.index + 1} of {presentation.total}</strong>}
        <span>Blinded: case, variant, effort and labels are hidden</span>
      </div>
    );
  }
  const kind = variantKindOf(trace.variant);
  return (
    <div className="row small">
      <Chip tone="neutral">case {caseId}</Chip>
      {entity && <Chip tone="neutral"><span className="entity-dot" style={{ background: entityColor(lexicon, entity) }} aria-hidden="true" />{entityDisplay(lexicon, entity)}</Chip>}
      <Chip tone={kind === 'base' ? 'neutral' : kind === 'authority' ? 'cue' : 'edited'} icon={kind === 'base' ? undefined : kind === 'authority' ? '▲' : '✎'}><span className="mono">{trace.variant}</span> {KIND_TEXT[kind]}</Chip>
      <Chip tone="neutral">effort {trace.effort as Effort}</Chip>
      <Chip tone="neutral">run {trace.run}</Chip>
      {modelTag && <Chip tone="neutral">model {modelTag}</Chip>}
      {trace.meta?.latency_ms != null && <Chip tone="neutral">{trace.meta.latency_ms} ms</Chip>}
      {runId && <span className="muted mono">{runId}</span>}
      {trace.meta?.error && <Chip tone="bad" icon="✗">error: {trace.meta.error}</Chip>}
    </div>
  );
}

export function KeyboardHelp({ shortcuts }: { shortcuts: Array<[string, string]> }) {
  const ref = useRef<HTMLDialogElement>(null);
  const [open, setOpen] = useState(false);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === '?' && !(e.target instanceof HTMLInputElement) && !(e.target instanceof HTMLTextAreaElement)) {
        e.preventDefault(); setOpen((o) => !o);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);
  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) d.showModal?.();
    if (!open && d.open) d.close();
  }, [open]);
  return (
    <>
      <button type="button" className="btn small" onClick={() => setOpen(true)} aria-haspopup="dialog" title="Keyboard shortcuts">Keys <kbd>?</kbd></button>
      <dialog ref={ref} onClose={() => setOpen(false)} aria-label="Keyboard shortcuts">
        <h2 style={{ marginTop: 0 }}>Keyboard shortcuts</h2>
        <table className="data">
          <tbody>
            {shortcuts.map(([k, d]) => (
              <tr key={k}><td><kbd>{k}</kbd></td><td>{d}</td></tr>
            ))}
          </tbody>
        </table>
        <div style={{ marginTop: 12, textAlign: 'right' }}>
          <button type="button" className="btn" onClick={() => setOpen(false)}>Close</button>
        </div>
      </dialog>
    </>
  );
}

export function Loading({ what }: { what: string }) {
  return <p className="muted" role="status" aria-live="polite">Loading {what}…</p>;
}
