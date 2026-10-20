import { useState, type ReactNode, type RefObject } from 'react';
import { downloadJson, downloadPng, downloadSvg } from '../lib/download';

export interface LegendKey { label: string; color?: string; shape?: 'dot' | 'square' | 'line' | 'dashed' | 'ring' | 'diamond' }
export interface DataTable { columns: string[]; rows: Array<Array<string | number | null>> }

interface Props {
  id: string;
  title: string;
  subtitle?: ReactNode;
  legend?: LegendKey[];
  table?: DataTable;
  exportData?: unknown;
  svgRef?: RefObject<SVGSVGElement>;
  children: ReactNode;
  /** Rendered between the chart and the footer (filters, notes). */
  aside?: ReactNode;
  headingLevel?: 2 | 3;
  flush?: boolean;
  tooltip?: ReactNode;
}

/** The common chart container: title, legend for ≥ 2 series, a Show data table, and SVG / PNG / JSON export. */
export function ChartFrame({ id, title, subtitle, legend, table, exportData, svgRef, children, aside, headingLevel = 2, flush = false, tooltip }: Props) {
  const [showData, setShowData] = useState(false);
  const H = headingLevel === 2 ? 'h2' : 'h3';
  const exportSvg = () => svgRef?.current && downloadSvg(`fig-${id}.svg`, svgRef.current);
  const exportPng = () => svgRef?.current && void downloadPng(`fig-${id}.png`, svgRef.current);
  const exportJson = () => downloadJson(`fig-${id}.json`, exportData ?? table ?? {});
  return (
    <figure className={`chart${flush ? ' flush' : ''}`} style={{ margin: 0 }} aria-labelledby={`${id}-title`}>
      <div className="chart-head">
        <H id={`${id}-title`}>{title}</H>
        {legend && legend.length >= 2 && (
          <ul className="legend" aria-label="Legend" style={{ margin: 0, padding: 0, listStyle: 'none' }}>
            {legend.map((k) => (
              <li key={k.label} className="key">
                <i className={k.shape === 'square' ? 'sq' : k.shape ?? ''} style={{ background: k.shape === 'dashed' || k.shape === 'ring' ? undefined : k.color, borderColor: k.color, color: k.color }} aria-hidden="true" />
                {k.label}
              </li>
            ))}
          </ul>
        )}
      </div>
      {subtitle && <p className="chart-sub">{subtitle}</p>}
      <div className="chart-body">{children}</div>
      {aside}
      <div className="chart-foot">
        {table ? (
          <details className="showdata" open={showData} onToggle={(e) => setShowData((e.target as HTMLDetailsElement).open)}>
            <summary>{showData ? 'Hide data' : 'Show data'}</summary>
            {showData && (
              <div className="table-scroll">
                <table className="data small">
                  <thead><tr>{table.columns.map((c) => <th key={c} className={/^(n|count|rate|share|low|high|point|lo|hi|\d)/i.test(c) ? 'num' : ''}>{c}</th>)}</tr></thead>
                  <tbody>
                    {table.rows.map((r, i) => (
                      <tr key={i}>{r.map((v, j) => <td key={j} className={typeof v === 'number' ? 'num' : ''}>{v === null || v === undefined ? '—' : typeof v === 'number' ? fmtNum(v) : v}</td>)}</tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </details>
        ) : <span />}
        <div className="chart-toolbar" aria-label={`Export ${title}`}>
          {svgRef && <button type="button" className="btn small quiet" onClick={exportSvg}>Export SVG</button>}
          {svgRef && <button type="button" className="btn small quiet" onClick={exportPng}>Export PNG</button>}
          <button type="button" className="btn small quiet" onClick={exportJson}>Export data</button>
        </div>
      </div>
      {tooltip}
    </figure>
  );
}

function fmtNum(v: number): string {
  if (Number.isInteger(v)) return String(v);
  return v.toFixed(3);
}
