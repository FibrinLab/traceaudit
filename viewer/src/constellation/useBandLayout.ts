import { useEffect, useMemo, useRef, useState } from 'react';
import { layoutBands, type CEdge, type CNode, type LayoutOptions, type Positioned } from './graph';
import type { LayoutRequest, LayoutResponse } from './layout.worker';

let worker: Worker | null | undefined;
function getWorker(): Worker | null {
  if (worker !== undefined) return worker;
  try {
    worker = new Worker(new URL('./layout.worker.ts', import.meta.url), { type: 'module' });
    worker.onerror = () => { worker = null; };
  } catch { worker = null; }
  return worker;
}

/** Lays out in a Web Worker when one is available (not from file:// or in tests), else synchronously. */
export function useBandLayout(nodes: CNode[], edges: CEdge[], opts: LayoutOptions): { positions: Map<string, Positioned>; ready: boolean } {
  const [state, setState] = useState<{ key: string; positions: Positioned[] } | null>(null);
  const key = useMemo(() => `${nodes.map((n) => n.id).join('|')}#${edges.length}#${opts.width}x${opts.height}#${opts.compact ? 'c' : ''}`, [nodes, edges, opts.width, opts.height, opts.compact]);
  const reqId = useRef(0);
  useEffect(() => {
    const w = getWorker();
    const id = ++reqId.current;
    if (!w) { setState({ key, positions: layoutBands(nodes, edges, opts) }); return; }
    const onMsg = (ev: MessageEvent<LayoutResponse>) => { if (ev.data.id === id) setState({ key, positions: ev.data.positions }); };
    w.addEventListener('message', onMsg);
    const onErr = () => { worker = null; setState({ key, positions: layoutBands(nodes, edges, opts) }); };
    w.addEventListener('error', onErr);
    w.postMessage({ id, nodes, edges, opts } satisfies LayoutRequest);
    return () => { w.removeEventListener('message', onMsg); w.removeEventListener('error', onErr); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  const positions = useMemo(() => new Map((state?.key === key ? state.positions : []).map((p) => [p.id, p])), [state, key]);
  return { positions, ready: state?.key === key };
}
