import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react';

interface TipState { x: number; y: number; content: ReactNode }

/** Position-following tooltip. `show` works for pointer and focus events alike; the same content on both. */
export function useTooltip() {
  const [tip, setTip] = useState<TipState | null>(null);
  const show = useCallback((e: { clientX?: number; clientY?: number; currentTarget?: EventTarget | null }, content: ReactNode) => {
    let x = e.clientX ?? 0, y = e.clientY ?? 0;
    if ((x === 0 && y === 0) && e.currentTarget && 'getBoundingClientRect' in (e.currentTarget as Element)) {
      const r = (e.currentTarget as Element).getBoundingClientRect();
      x = r.left + r.width / 2; y = r.top;
    }
    setTip({ x, y, content });
  }, []);
  const move = useCallback((e: { clientX: number; clientY: number }) => {
    setTip((t) => (t ? { ...t, x: e.clientX, y: e.clientY } : t));
  }, []);
  const hide = useCallback(() => setTip(null), []);
  const node = tip ? <TooltipBox x={tip.x} y={tip.y}>{tip.content}</TooltipBox> : null;
  return { show, move, hide, node, visible: !!tip };
}

function TooltipBox({ x, y, children }: { x: number; y: number; children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState({ left: x + 14, top: y + 14 });
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    let left = x + 14, top = y + 14;
    if (left + r.width > window.innerWidth - 8) left = x - r.width - 14;
    if (top + r.height > window.innerHeight - 8) top = y - r.height - 14;
    setPos({ left: Math.max(8, left), top: Math.max(8, top) });
  }, [x, y, children]);
  return <div ref={ref} className="tooltip" role="tooltip" style={pos}>{children}</div>;
}

export function TipRow({ color, label, value }: { color?: string; label: ReactNode; value: ReactNode }) {
  return (
    <div className="tt-row">
      {color && <i style={{ background: color }} aria-hidden="true" />}
      <strong>{value}</strong>
      <span className="muted">{label}</span>
    </div>
  );
}
