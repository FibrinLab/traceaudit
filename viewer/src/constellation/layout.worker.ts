// Web Worker: runs the band-constrained layout off the main thread.
import { layoutBands, type CEdge, type CNode, type LayoutOptions } from './graph';

export interface LayoutRequest { id: number; nodes: CNode[]; edges: CEdge[]; opts: LayoutOptions }
export interface LayoutResponse { id: number; positions: Array<{ id: string; x: number; y: number }> }

self.onmessage = (ev: MessageEvent<LayoutRequest>) => {
  const { id, nodes, edges, opts } = ev.data;
  const positions = layoutBands(nodes, edges, opts);
  (self as unknown as Worker).postMessage({ id, positions } satisfies LayoutResponse);
};
