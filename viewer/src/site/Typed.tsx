import { useEffect, useState, type ElementType } from 'react';

/** True when motion should be skipped: the visitor asked for reduced motion, or there is no matchMedia (tests). */
export function motionReduced(): boolean {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return true;
  try { return window.matchMedia('(prefers-reduced-motion: reduce)').matches; } catch { return true; }
}

/** Reveal `text` one character at a time, like a typewriter. `enabled: false` holds the text back (nothing shown). */
export function useTyped(text: string, { speed = 28, startDelay = 0, enabled = true }: { speed?: number; startDelay?: number; enabled?: boolean } = {}): { shown: string; done: boolean } {
  const immediate = motionReduced();
  const [n, setN] = useState(() => (enabled && immediate ? text.length : 0));
  useEffect(() => {
    if (!enabled) { setN(0); return; }
    if (immediate) { setN(text.length); return; }
    setN(0);
    let i = 0;
    let timer: number | undefined;
    const tick = () => {
      i += 1;
      setN(i);
      if (i < text.length) {
        // Pauses after sentence marks read as a typist breathing, not a machine.
        const ch = text[i - 1];
        const pause = ch === '.' || ch === '?' || ch === '\n' ? speed * 9 : ch === ',' ? speed * 4 : speed;
        timer = window.setTimeout(tick, pause);
      }
    };
    timer = window.setTimeout(tick, startDelay);
    return () => { if (timer !== undefined) window.clearTimeout(timer); };
  }, [text, speed, startDelay, enabled, immediate]);
  return { shown: text.slice(0, n), done: n >= text.length };
}

/** A typed line with a block cursor that blinks while typing and fades once done. */
export function Typed({ text, as: Tag = 'span', speed, startDelay, enabled = true, cursor = true, className }: {
  text: string; as?: ElementType; speed?: number; startDelay?: number; enabled?: boolean; cursor?: boolean; className?: string;
}) {
  const { shown, done } = useTyped(text, { speed, startDelay, enabled });
  return (
    <Tag className={className} aria-label={text}>
      <span aria-hidden="true">{shown}</span>
      {cursor && enabled && <span aria-hidden="true" className={`cursor${done ? ' done' : ''}`} />}
    </Tag>
  );
}
