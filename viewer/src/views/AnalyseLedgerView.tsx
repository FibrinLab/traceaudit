import { useCallback, useMemo, useRef, useState, type ChangeEvent, type ReactNode } from 'react';
import { describeError } from '../lib/api';
import { useApi } from '../lib/useApiSettings';
import { downloadJson } from '../lib/download';
import { Banner, Chip } from '../components/Shared';
import { AnalysePage } from './AnalyseView';
import {
  COVERAGE_META, COVERAGE_ORDER, GRADE_ICON, GRADE_TEXT, LEDGER_FILTERS,
  candidateCounts, coverageCategory, coverageCounts, disagreeingIds, factLabel, factMap, filterFacts, gradeTone, groupFacts, isCaseFact, sourceText, tokeniseThinking,
  type Citation, type CoverageCategory, type Fact, type LedgerFilter, type LedgerRequest, type LedgerResult,
  describeUncited,
} from '../lib/ledger';

/** The service's own fixture: a haematopathology trace with 111 facts, packaged with the viewer. */
const EXAMPLE_URL = './examples/enable-trace-case_003.md';

type Busy = 'idle' | 'example' | 'audit';

/** `{case, trace}` JSON is sent structured; anything else is the artefact text. */
export function buildLedgerRequest(text: string): LedgerRequest {
  const t = text.trim();
  if (t.startsWith('{')) {
    try {
      const parsed = JSON.parse(t) as Record<string, unknown>;
      if (parsed && typeof parsed === 'object' && parsed.case && typeof parsed.case === 'object' && parsed.trace && typeof parsed.trace === 'object') {
        return { case: parsed.case as Record<string, unknown>, trace: parsed.trace as Record<string, unknown> };
      }
    } catch { /* not JSON: treat as markdown */ }
  }
  return { markdown: text };
}

export function AnalyseLedgerView() {
  const api = useApi();
  const [text, setText] = useState('');
  const [busy, setBusy] = useState<Busy>('idle');
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [result, setResult] = useState<{ res: LedgerResult; at: string } | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const working = busy !== 'idle';

  const loadExample = async () => {
    setBusy('example'); setError(null); setNotice(null);
    try {
      const r = await fetch(EXAMPLE_URL, { cache: 'no-cache' });
      if (!r.ok) throw new Error(`HTTP ${r.status} loading the example artefact`);
      const md = await r.text();
      setText(md); setResult(null);
      setNotice('Loaded the example artefact (case_003, a reasoning trace with 111 facts). Press Audit to check it.');
    } catch (e) { setError(describeError(e)); } finally { setBusy('idle'); }
  };
  const onFile = async (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file) return;
    setError(null); setNotice(null);
    try {
      const t = await file.text();
      setText(t); setResult(null);
      setNotice(`Loaded ${file.name} (${Math.round(t.length / 1024)} KB). Press Audit to check it.`);
    } catch (err) { setError(describeError(err)); }
  };
  const clear = () => { setText(''); setResult(null); setError(null); setNotice(null); };
  const audit = async () => {
    setError(null); setNotice(null);
    if (!text.trim()) { setError('Paste a trace artefact first: the markdown the trace runner wrote, or a {case, trace} JSON document.'); return; }
    setBusy('audit'); setResult(null);
    try {
      const res = await api.auditLedger(buildLedgerRequest(text));
      setResult({ res, at: new Date().toISOString() });
    } catch (e) { setError(describeError(e)); } finally { setBusy('idle'); }
  };
  const exportJson = () => {
    if (!result) return;
    downloadJson(`ledger-${result.res.case_id ?? 'trace'}-${result.at.replace(/[:.]/g, '-')}.json`, result.res);
  };

  return (
    <AnalysePage active="ledger" title="Audit a structured trace" wide lede="Paste a trace artefact: its facts with ids, the reasoning that cites them, the delivered report with citation ids, the rationale and the ablation. Every citation is checked against its fact. No model is called.">
      <form className="panel" aria-labelledby="ledger-form-title" onSubmit={(e) => { e.preventDefault(); void audit(); }}>
        <div className="panel-head">
          <h2 id="ledger-form-title" style={{ margin: 0 }}>Trace artefact</h2>
          <div className="row small">
            <button type="button" className="btn small" onClick={() => void loadExample()} disabled={working}>{busy === 'example' ? 'Loading…' : 'Load example'}</button>
            <button type="button" className="btn small" onClick={() => fileInput.current?.click()} disabled={working}>Choose file</button>
            <input ref={fileInput} type="file" accept=".md,.markdown,.json,text/markdown,application/json" className="visually-hidden" aria-label="Choose a trace artefact (.md or .json)" onChange={(e) => void onFile(e)} />
            <button type="button" className="btn small quiet" onClick={clear} disabled={working}>Clear</button>
          </div>
        </div>
        <label className="field block full">
          <span>Artefact (markdown, or a <code>{'{case, trace}'}</code> JSON document)</span>
          <textarea className="ledger" value={text} onChange={(e) => setText(e.target.value)} spellCheck={false} placeholder={'# Reasoning trace — case_… \n\n## 1. Available information\n| ids | field | value | evidence snippet |\n| p_1 | CD5 | Positive | positive for CD5 |\n…'} required />
        </label>
        {error && <Banner tone="bad">{error}</Banner>}
        {notice && !error && <Banner tone="info">{notice}</Banner>}
        <div className="actions" style={{ marginTop: 12 }}>
          <button type="submit" className="btn primary" disabled={working}>{busy === 'audit' ? 'Auditing…' : 'Audit'}</button>
          <span className="small muted">Sends the artefact to {api.settings.base || 'this origin'} at /api/ledger. No model is called.</span>
        </div>
      </form>

      {result && (
        <section aria-labelledby="ledger-result-title" style={{ marginTop: 24 }}>
          <div className="panel-head">
            <h2 id="ledger-result-title" style={{ margin: 0 }}>Result{result.res.case_id ? <span className="muted" style={{ fontWeight: 400 }}> · {result.res.case_id}</span> : null}</h2>
            <div className="row small">
              <nav aria-label="Result blocks" className="row small ledger-jump">
                {[['verdict', 'Verdict'], ['report', 'Report'], ['ledger', 'Ledger'], ['reasoning', 'Reasoning'], ['rationale', 'Rationale'], ['ablation', 'Ablation'], ['coverage', 'Coverage']].map(([id, label]) => <a key={id} href={`#ledger-${id}`} onClick={(e) => { e.preventDefault(); document.getElementById(`ledger-${id}`)?.scrollIntoView({ block: 'start' }); }}>{label}</a>)}
              </nav>
              <button type="button" className="btn small" onClick={exportJson}>Export result JSON</button>
            </div>
          </div>
          <LedgerResultView result={result.res} />
        </section>
      )}
    </AnalysePage>
  );
}

// ---- result page -------------------------------------------------------------------------------------

interface Ctx {
  facts: Map<string, Fact>;
  highlight: string | null;
  selected: string | null;
  setHighlight: (id: string | null) => void;
  scrollToFact: (id: string) => void;
}

export function LedgerResultView({ result }: { result: LedgerResult }) {
  const [highlight, setHighlight] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [filter, setFilter] = useState<LedgerFilter>('all');
  const [search, setSearch] = useState('');
  const facts = useMemo(() => factMap(result.facts), [result.facts]);
  const disagreeing = useMemo(() => disagreeingIds(result.sections), [result.sections]);
  const visible = useMemo(() => filterFacts(result.facts, filter, search, disagreeing), [result.facts, filter, search, disagreeing]);
  const visibleIds = useMemo(() => new Set(visible.map((f) => f.id)), [visible]);

  const scrollToFact = useCallback((id: string) => {
    if (!facts.has(id)) return;
    const go = () => {
      const el = document.getElementById(`fact-${id}`);
      if (!el) return;
      el.scrollIntoView({ block: 'center' });
      (el as HTMLElement).focus({ preventScroll: true });
    };
    setSelected(id);
    if (!visibleIds.has(id)) { setFilter('all'); setSearch(''); requestAnimationFrame(() => requestAnimationFrame(go)); } else go();
  }, [facts, visibleIds]);

  const ctx: Ctx = { facts, highlight, selected, setHighlight, scrollToFact };

  return (
    <div className="stack ledger-result" style={{ gap: 24 }}>
      <VerdictStrip result={result} />
      <ReportWithCitations result={result} ctx={ctx} />
      <FactLedgerTable result={result} ctx={ctx} visible={visible} filter={filter} setFilter={setFilter} search={search} setSearch={setSearch} disagreeing={disagreeing} />
      <ReasoningBlock result={result} ctx={ctx} />
      <RationaleBlock result={result} ctx={ctx} />
      <AblationBlock result={result} ctx={ctx} />
      <CoverageStrip result={result} ctx={ctx} />
    </div>
  );
}

function Block({ id, title, sub, children, aside }: { id: string; title: string; sub?: ReactNode; children: ReactNode; aside?: ReactNode }) {
  return (
    <section className="panel ledger-block" id={`ledger-${id}`} aria-labelledby={`ledger-${id}-title`}>
      <div className="panel-head">
        <div><h2 id={`ledger-${id}-title`}>{title}</h2>{sub && <div className="sub">{sub}</div>}</div>
        {aside}
      </div>
      {children}
    </section>
  );
}

// a. Verdict ------------------------------------------------------------------------------------------

function VerdictStrip({ result }: { result: LedgerResult }) {
  const [open, setOpen] = useState<string | null>(null);
  const { decision, truth, metrics, checks } = result;
  const match = decision != null && truth != null ? decision === truth : null;
  const openCheck = checks.find((c) => c.id === open) ?? null;
  return (
    <Block id="verdict" title="Verdict" sub={`${metrics.facts} facts: ${metrics.patient_facts} patient, ${metrics.context_facts} context, ${metrics.reference_facts} reference · ${metrics.cited_in_report} cited in the report`}>
      <div className="verdict-strip">
        <div className="tile">
          <span className="label">Decision</span>
          <span className="value verdict-value">{decision ?? '—'}</span>
        </div>
        <div className="tile">
          <span className="label">Ground truth</span>
          <span className="value verdict-value">{truth ?? 'not stated'}</span>
        </div>
        <div className="tile">
          <span className="label">Agreement</span>
          <span style={{ marginTop: 6 }}>
            {match === true ? <Chip tone="good" icon="✓" className="badge-lg">matches truth</Chip> : match === false ? <Chip tone="bad" icon="✗" className="badge-lg">differs from truth</Chip> : <Chip tone="neutral" className="badge-lg">no truth to compare</Chip>}
          </span>
        </div>
        <div className="tile">
          <span className="label">Checks failed</span>
          <span className="value num"><span style={{ color: metrics.checks_failed ? 'var(--contradicted)' : 'var(--supported)' }}>{metrics.checks_failed}</span><span className="muted" style={{ fontSize: 'var(--fs-2)', fontWeight: 400 }}> / {metrics.checks_total}</span></span>
        </div>
      </div>
      <div className="row check-chips" role="list" aria-label="Checks" style={{ gap: 6, marginTop: 14 }}>
        {checks.map((c) => (
          <button key={c.id} type="button" role="listitem" className={`chip check ${c.status === 'PASS' ? 'good' : 'bad'}`} aria-expanded={open === c.id} aria-controls="check-detail" onClick={() => setOpen(open === c.id ? null : c.id)} title={c.detail || c.title}>
            <span className="icon" aria-hidden="true">{c.status === 'PASS' ? '✓' : '✗'}</span>{c.title}
          </button>
        ))}
      </div>
      <div id="check-detail" className={`check-detail ${openCheck ? '' : 'empty'}`} aria-live="polite">
        {openCheck && (
          <>
            <div className="row" style={{ gap: 8 }}>
              <Chip tone={openCheck.status === 'PASS' ? 'good' : 'bad'} icon={openCheck.status === 'PASS' ? '✓' : '✗'}>{openCheck.status}</Chip>
              <strong>{openCheck.title}</strong>
              <span className="muted mono small">{openCheck.id}</span>
            </div>
            <p style={{ margin: '6px 0 0', maxWidth: 'none', overflowWrap: 'anywhere' }}>{openCheck.detail || <span className="muted">No detail: the check has nothing to report.</span>}</p>
          </>
        )}
      </div>
    </Block>
  );
}

// b. Report -------------------------------------------------------------------------------------------

/** A citation drawn as a chip coloured by grade; hover or focus highlights the fact row, click scrolls to it. */
function CitationChip({ c, ctx }: { c: Citation; ctx: Ctx }) {
  const f = ctx.facts.get(c.id);
  const grade = f || c.grade !== 'agree' ? c.grade : 'not_found';
  const tone = gradeTone(f ? grade : 'not_found');
  const label = factLabel(c.id, f ?? { field: c.field, value: c.value });
  const title = `${GRADE_TEXT[f ? grade : 'not_found']}${c.stated ? ` · stated: ${c.stated}` : ''}`;
  return (
    <button type="button" className={`chip fact-chip ${tone} ${ctx.highlight === c.id ? 'is-hl' : ''}`} title={title} aria-label={`${label}: ${title}`}
      onMouseEnter={() => ctx.setHighlight(c.id)} onMouseLeave={() => ctx.setHighlight(null)} onFocus={() => ctx.setHighlight(c.id)} onBlur={() => ctx.setHighlight(null)}
      onClick={() => ctx.scrollToFact(c.id)} disabled={!f}>
      <span className="icon" aria-hidden="true">{GRADE_ICON[f ? grade : 'not_found']}</span>
      <span className="mono">{c.id}</span>{f || c.field ? <span className="fact-kv"> · {f?.field ?? c.field} = {f?.value ?? c.value ?? '—'}</span> : null}
    </button>
  );
}

/** A plain fact-id chip (rationale, ablation, thinking): neutral, with the fact's field and value when known. */
function FactChip({ id, ctx, warn, compact = false }: { id: string; ctx: Ctx; warn?: string; compact?: boolean }) {
  const f = ctx.facts.get(id);
  const tone = !f ? 'bad outline' : warn ? 'warn' : 'neutral';
  const label = factLabel(id, f);
  return (
    <button type="button" className={`chip fact-chip ${tone} ${ctx.highlight === id ? 'is-hl' : ''}`} title={warn ?? (f ? label : GRADE_TEXT.not_found)} aria-label={`${label}${warn ? `: ${warn}` : ''}`}
      onMouseEnter={() => ctx.setHighlight(id)} onMouseLeave={() => ctx.setHighlight(null)} onFocus={() => ctx.setHighlight(id)} onBlur={() => ctx.setHighlight(null)}
      onClick={() => ctx.scrollToFact(id)} disabled={!f}>
      {warn && <span className="icon" aria-hidden="true">⚠</span>}
      {!f && <span className="icon" aria-hidden="true">∅</span>}
      <span className="mono">{id}</span>{f && !compact ? <span className="fact-kv"> · {f.field} = {f.value}</span> : null}
    </button>
  );
}

function ReportWithCitations({ result, ctx }: { result: LedgerResult; ctx: Ctx }) {
  const m = result.metrics;
  return (
    <Block id="report" title="Report with citations" sub={<>{m.cited_in_report} citations: <span style={{ color: 'var(--supported)' }}>{m.cited_agree} agree</span>, <span style={{ color: 'var(--contradicted)' }}>{m.cited_disagree} disagree</span>, <span style={{ color: 'var(--unsupported)' }}>{m.cited_unverifiable} unverifiable</span>. Hover a chip to find its fact; click to jump to it.</>}
      aside={<GradeLegend />}>
      {result.sections.length === 0 && <p className="muted">The artefact carries no delivered report.</p>}
      {result.sections.map((s, si) => (
        <div key={si} className="ledger-section">
          <h3>{s.title}</h3>
          {s.segments.map((seg, i) => (
            <div key={i} className={`ledger-seg ${seg.informative ? '' : 'quiet'}`}>
              <p className="seg-text">{seg.text}{!seg.informative && <span className="muted small"> (not informative)</span>}</p>
              <div className="row" style={{ gap: 6 }}>
                {seg.cited.map((c, ci) => <CitationChip key={`${c.id}-${ci}`} c={c} ctx={ctx} />)}
                {seg.citation_ids.filter((id) => !seg.cited.some((c) => c.id === id)).map((id) => <CitationChip key={id} c={{ id, grade: 'not_found' }} ctx={ctx} />)}
                {seg.cited.length === 0 && seg.citation_ids.length === 0 && <span className="muted small">no citations</span>}
              </div>
              {seg.uncited_assertions.length > 0 && (
                <ul className="uncited" aria-label="Uncited assertions">
                  {seg.uncited_assertions.map((a, ai) => <li key={ai}><span className="icon" aria-hidden="true">!</span> uncited: {describeUncited(a)} <span className="muted small">({a.grade})</span></li>)}
                </ul>
              )}
            </div>
          ))}
        </div>
      ))}
    </Block>
  );
}

function GradeLegend() {
  return (
    <div className="legend" aria-label="Citation grades">
      {(['agree', 'disagree', 'unverifiable', 'not_mentioned', 'reference', 'not_found'] as const).map((g) => (
        <span key={g} className={`chip ${gradeTone(g)}`} style={{ cursor: 'default' }}><span className="icon" aria-hidden="true">{GRADE_ICON[g]}</span>{g.replace('_', ' ')}</span>
      ))}
    </div>
  );
}

// c. Fact ledger ----------------------------------------------------------------------------------------

const EVIDENCE_CUT = 72;

function FactLedgerTable({ result, ctx, visible, filter, setFilter, search, setSearch, disagreeing }: {
  result: LedgerResult; ctx: Ctx; visible: Fact[]; filter: LedgerFilter; setFilter: (f: LedgerFilter) => void; search: string; setSearch: (s: string) => void; disagreeing: Set<string>;
}) {
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set());
  const groups = useMemo(() => groupFacts(visible), [visible]);
  const counts = useMemo<Record<LedgerFilter, number>>(() => ({
    all: result.facts.length,
    ignored: result.facts.filter((f) => f.ignored).length,
    ignored_informative: result.facts.filter((f) => f.ignored && f.informative).length,
    cited: result.facts.filter((f) => f.cited_in_report || f.cited_in_rationale).length,
    disagreements: disagreeing.size,
  }), [result.facts, disagreeing]);
  const toggle = (id: string) => setExpanded((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n; });

  return (
    <Block id="ledger" title="Fact ledger" sub={`${visible.length} of ${result.facts.length} facts shown · ${result.metrics.ignored} ignored, ${result.metrics.ignored_informative} of them informative. Marks: T referenced in thinking, R cited in report, A cited in rationale, I informative.`}>
      <div className="filters" style={{ marginBottom: 12 }}>
        <div className="row" role="group" aria-label="Filter facts" style={{ gap: 6 }}>
          {LEDGER_FILTERS.map(([id, label]) => (
            <button key={id} type="button" className="chip filter" aria-pressed={filter === id} onClick={() => setFilter(id)}>{label} <span className="num muted">{counts[id]}</span></button>
          ))}
        </div>
        <span className="spacer" />
        <label className="field">
          <span className="visually-hidden">Search facts</span>
          <input type="search" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search id, field, value, evidence…" aria-label="Search facts" style={{ minWidth: 260 }} />
        </label>
      </div>
      <div className="table-scroll">
        <table className="data ledger-table">
          <thead>
            <tr>
              <th scope="col">id</th><th scope="col">field</th><th scope="col">value</th><th scope="col">evidence</th>
              <th scope="col" className="mark-cell" title="Referenced in thinking" abbr="thinking">T</th>
              <th scope="col" className="mark-cell" title="Cited in report" abbr="report">R</th>
              <th scope="col" className="mark-cell" title="Cited in rationale" abbr="rationale">A</th>
              <th scope="col" className="mark-cell" title="Informative" abbr="informative">I</th>
            </tr>
          </thead>
          {groups.map((g) => (
            <tbody key={`${g.source}/${g.section}`}>
              <tr className="group"><th scope="rowgroup" colSpan={8}>{sourceText(g.source)} <span className="sep" aria-hidden="true">›</span> {g.section} <span className="muted num">({g.facts.length})</span></th></tr>
              {g.facts.map((f) => {
                const long = f.evidence.length > EVIDENCE_CUT;
                const open = expanded.has(f.id);
                const dis = disagreeing.has(f.id);
                return (
                  <tr key={f.id} id={`fact-${f.id}`} tabIndex={-1}
                    className={`fact-row ${f.ignored ? (f.informative ? 'ignored' : 'ignored untested') : ''} ${ctx.highlight === f.id ? 'is-hl' : ''} ${ctx.selected === f.id ? 'is-selected' : ''} ${dis ? 'disagrees' : ''}`}
                    onMouseEnter={() => ctx.setHighlight(f.id)} onMouseLeave={() => ctx.setHighlight(null)}>
                    <td className="mono">{f.id}{f.ignored && <span className="visually-hidden"> (ignored)</span>}</td>
                    <td>{f.field}{f.candidate && <span className="muted small"> · {f.candidate}</span>}</td>
                    <td>{f.value}{dis && <> <Chip tone="bad" icon="✗">misstated</Chip></>}</td>
                    <td className="evidence">
                      {f.evidence ? (long && !open ? `${f.evidence.slice(0, EVIDENCE_CUT)}… ` : f.evidence) : <span className="muted">—</span>}
                      {long && <button type="button" className="btn small quiet" aria-expanded={open} onClick={() => toggle(f.id)}>{open ? 'less' : 'more'}</button>}
                    </td>
                    <Mark on={f.referenced_in_thinking} text="referenced in thinking" />
                    <Mark on={f.cited_in_report} text="cited in report" />
                    <Mark on={f.cited_in_rationale} text="cited in rationale" />
                    <Mark on={f.informative} text="informative" />
                  </tr>
                );
              })}
            </tbody>
          ))}
          {visible.length === 0 && <tbody><tr><td colSpan={8} className="muted">No facts match this filter.</td></tr></tbody>}
        </table>
      </div>
    </Block>
  );
}

function Mark({ on, text }: { on: boolean; text: string }) {
  return <td className="mark-cell"><span className={`mk ${on ? 'on' : ''}`} aria-hidden="true">{on ? '●' : '○'}</span><span className="visually-hidden">{on ? text : `not ${text}`}</span></td>;
}

// d. Reasoning -------------------------------------------------------------------------------------------

function ReasoningBlock({ result, ctx }: { result: LedgerResult; ctx: Ctx }) {
  const thinking = result.thinking;
  const allCandidates = useMemo(() => [...new Set([...(result.candidates ?? []), ...(thinking?.candidates ?? [])])], [result.candidates, thinking]);
  const tokens = useMemo(() => thinking ? tokeniseThinking(thinking.text, ctx.facts.keys(), allCandidates) : [], [thinking, ctx.facts, allCandidates]);
  const counts = useMemo(() => thinking ? candidateCounts(thinking.text, allCandidates) : {}, [thinking, allCandidates]);
  const named = allCandidates.filter((c) => (counts[c] ?? 0) > 0 || thinking?.candidates.includes(c));
  if (!thinking) return <Block id="reasoning" title="Reasoning"><p className="muted">The artefact carries no reasoning text.</p></Block>;
  return (
    <Block id="reasoning" title="Reasoning" sub={`${result.metrics.thinking_chars.toLocaleString()} characters · ${result.metrics.thinking_ids} fact ids named · ${named.length} of ${allCandidates.length} candidates named. Click an id to jump to its fact.`}>
      <div className="ledger-reasoning">
        <div className="trace-text thinking" aria-label="Thinking text">
          {tokens.map((t, i) => t.kind === 'text' ? <span key={i}>{t.text}</span>
            : t.kind === 'id' ? <FactChip key={i} id={t.id} ctx={ctx} compact />
            : <mark key={i} className="hl hl-cue" title={`candidate: ${t.candidate}`}>{t.text}</mark>)}
        </div>
        <aside aria-labelledby="candidates-title">
          <h3 id="candidates-title" style={{ marginTop: 0 }}>Candidates considered</h3>
          <table className="data">
            <thead><tr><th scope="col">candidate</th><th scope="col" className="num">named</th></tr></thead>
            <tbody>
              {allCandidates.map((c) => {
                const n = counts[c] ?? 0;
                const isDecision = c === result.decision;
                return (
                  <tr key={c} className={n ? '' : 'muted'}>
                    <td>{n ? <mark className="hl hl-cue">{c}</mark> : c}{isDecision && <> <Chip tone="neutral" icon="→">decision</Chip></>}{c === result.truth && c !== result.decision && <> <Chip tone="neutral">truth</Chip></>}</td>
                    <td className="num">{n || <span className="muted">not named</span>}</td>
                  </tr>
                );
              })}
              {allCandidates.length === 0 && <tr><td colSpan={2} className="muted">No candidate list in the artefact.</td></tr>}
            </tbody>
          </table>
          {named.length <= 1 && allCandidates.length > 1 && <p className="small muted" style={{ marginTop: 8 }}>Only one candidate is named: the thinking did not weigh alternatives.</p>}
        </aside>
      </div>
    </Block>
  );
}

// e. Rationale -------------------------------------------------------------------------------------------

const VERDICT_TONE: Record<string, string> = { favoured: 'good', likely: 'good', possible: 'warn', unlikely: 'neutral', excluded: 'neutral' };
const CRITERION: Record<string, { tone: string; icon: string; text: string }> = {
  met: { tone: 'good', icon: '✓', text: 'met' },
  not_met: { tone: 'bad', icon: '✗', text: 'not met' },
  not_assessable: { tone: 'neutral', icon: '?', text: 'not assessable' },
};
const criterionMeta = (s: string) => CRITERION[s] ?? { tone: 'neutral', icon: '·', text: s.replace(/_/g, ' ') };

function RationaleBlock({ result, ctx }: { result: LedgerResult; ctx: Ctx }) {
  const [open, setOpen] = useState<Set<string>>(() => new Set());
  const r = result.rationale;
  if (!r) return <Block id="rationale" title="Rationale"><p className="muted">The artefact carries no rationale.</p></Block>;
  const toggle = (d: string) => setOpen((s) => { const n = new Set(s); if (n.has(d)) n.delete(d); else n.add(d); return n; });
  const ids = (list: string[]) => list.map((id) => <FactChip key={id} id={id} ctx={ctx} compact />);
  return (
    <Block id="rationale" title="Rationale" sub={<>Rationale decision <strong>{r.decision ?? '—'}</strong>{r.confidence ? <>, confidence {r.confidence}</> : null}. Contradicting chips carry ⚠ when the fact is not informative.</>}>
      <div className="table-scroll">
        <table className="data differential">
          <thead>
            <tr><th scope="col" style={{ width: 28 }}><span className="visually-hidden">criteria</span></th><th scope="col">diagnosis</th><th scope="col">verdict</th><th scope="col">supporting</th><th scope="col">contradicting</th><th scope="col">criteria</th></tr>
          </thead>
          <tbody>
            {r.differential.map((d) => {
              const isOpen = open.has(d.diagnosis);
              const met = d.criteria.filter((c) => c.status === 'met').length;
              const notMet = d.criteria.filter((c) => c.status === 'not_met').length;
              const na = d.criteria.length - met - notMet;
              return [
                <tr key={d.diagnosis} className={d.verdict === 'favoured' ? 'favoured' : ''}>
                  <td><button type="button" className="btn small quiet" aria-expanded={isOpen} aria-controls={`crit-${slug(d.diagnosis)}`} onClick={() => toggle(d.diagnosis)} aria-label={`${isOpen ? 'Hide' : 'Show'} criteria for ${d.diagnosis}`}>{isOpen ? '▾' : '▸'}</button></td>
                  <td><strong>{d.diagnosis}</strong></td>
                  <td><Chip tone={VERDICT_TONE[d.verdict] ?? 'neutral'} icon={d.verdict === 'favoured' ? '★' : undefined}>{d.verdict}</Chip></td>
                  <td><div className="row" style={{ gap: 4 }}>{d.supporting.length ? ids(d.supporting) : <span className="muted">—</span>}</div></td>
                  <td><div className="row" style={{ gap: 4 }}>{d.contradicting.length ? d.contradicting.map((id) => {
                    const f = ctx.facts.get(id);
                    return <FactChip key={id} id={id} ctx={ctx} compact warn={f && !f.informative ? `cited as contradicting, but ${id} is not informative (${f.field} = ${f.value})` : undefined} />;
                  }) : <span className="muted">—</span>}</div></td>
                  <td className="criteria-counts">
                    <span className="num" style={{ color: 'var(--supported)' }}>{met} met</span> · <span className="num" style={{ color: notMet ? 'var(--contradicted)' : undefined }}>{notMet} not met</span> · <span className="num muted">{na} n/a</span>
                  </td>
                </tr>,
                isOpen && (
                  <tr key={`${d.diagnosis}-criteria`} className="criteria-row" id={`crit-${slug(d.diagnosis)}`}>
                    <td /><td colSpan={5}>
                      {d.rationale && <p style={{ margin: '0 0 8px', maxWidth: '80ch' }}>{d.rationale}</p>}
                      {d.criteria.length ? (
                        <ul className="criteria">
                          {d.criteria.map((c, i) => { const m = criterionMeta(c.status); return (
                            <li key={i}><Chip tone={m.tone} icon={m.icon}>{m.text}</Chip> <span>{c.criterion}</span> <span className="row" style={{ gap: 4, display: 'inline-flex' }}>{ids(c.ids)}</span></li>
                          ); })}
                        </ul>
                      ) : <p className="muted" style={{ margin: 0 }}>No criteria listed.</p>}
                    </td>
                  </tr>
                ),
              ];
            })}
            {r.differential.length === 0 && <tr><td colSpan={6} className="muted">No differential.</td></tr>}
          </tbody>
        </table>
      </div>
      <div className="grid-2" style={{ marginTop: 18 }}>
        <div>
          <h3>Key findings</h3>
          {r.key_findings.length ? (
            <ul className="fact-list">{r.key_findings.map((k, i) => <li key={i}>{k.modality && <span className="muted small">{k.modality} · </span>}{k.description} <span className="row" style={{ gap: 4, display: 'inline-flex' }}>{ids(k.ids)}</span></li>)}</ul>
          ) : <p className="muted">None stated.</p>}
          <h3>Discriminators</h3>
          {r.discriminators.length ? (
            <ul className="fact-list">{r.discriminators.map((d, i) => <li key={i}>{d.text} <span className="row" style={{ gap: 4, display: 'inline-flex' }}>{ids(d.ids)}</span></li>)}</ul>
          ) : <p className="muted">None stated.</p>}
        </div>
        <div>
          <h3>Unresolved</h3>
          {r.unresolved.length ? <ul className="fact-list">{r.unresolved.map((u, i) => <li key={i}>{u}</li>)}</ul> : <p className="muted">Nothing marked unresolved.</p>}
          <h3>What would change the answer</h3>
          {r.would_change.length ? <ul className="fact-list">{r.would_change.map((u, i) => <li key={i}>{u}</li>)}</ul> : <p className="muted">Not stated.</p>}
        </div>
      </div>
    </Block>
  );
}
const slug = (s: string) => s.toLowerCase().replace(/[^a-z0-9]+/g, '-');

// f. Ablation ---------------------------------------------------------------------------------------------

function AblationBlock({ result, ctx }: { result: LedgerResult; ctx: Ctx }) {
  const a = result.ablation;
  if (!a) return <Block id="ablation" title="Ablation"><p className="muted">The artefact carries no ablation.</p></Block>;
  return (
    <Block id="ablation" title="Ablation" sub="The stated discriminators were removed from the facts and the decision re-derived.">
      <div className="ablation">
        <div>
          <div className="small muted" style={{ marginBottom: 4 }}>Removed facts ({a.removed_ids.length})</div>
          <div className="row" style={{ gap: 6 }}>{a.removed_ids.length ? a.removed_ids.map((id) => <FactChip key={id} id={id} ctx={ctx} />) : <span className="muted">none</span>}</div>
        </div>
        <div className="before-after" aria-label="Decision before and after">
          <div className="tile"><span className="label">before</span><span className="value verdict-value">{a.decision_before ?? '—'}</span></div>
          <span className="arrow" aria-hidden="true">→</span>
          <div className="tile"><span className="label">after</span><span className="value verdict-value">{a.decision_after ?? '—'}</span></div>
          <div className="tile">
            <span className="label">verdict</span>
            <span style={{ marginTop: 6 }}>{a.changed
              ? <Chip tone="good" icon="✓" className="badge-lg">load-bearing</Chip>
              : <Chip tone="warn" icon="!" className="badge-lg">not load-bearing</Chip>}</span>
          </div>
        </div>
        <p className="muted" style={{ margin: 0 }}>{a.changed
          ? 'The decision changed without these facts: the rationale\'s discriminators carry the answer.'
          : 'The decision survived without these facts: the rationale\'s stated discriminators are not what the answer rests on.'}</p>
      </div>
    </Block>
  );
}

// g. Coverage ------------------------------------------------------------------------------------------------

function CoverageStrip({ result, ctx }: { result: LedgerResult; ctx: Ctx }) {
  const caseFacts = useMemo(() => result.facts.filter(isCaseFact), [result.facts]);
  const counts = useMemo(() => coverageCounts(result.facts), [result.facts]);
  const total = caseFacts.length;
  return (
    <Block id="coverage" title="Coverage" sub={`One square per patient or context fact, in ledger order (${total}). Click a square to jump to the fact.`}
      aside={
        <div className="legend" aria-label="Coverage legend">
          {COVERAGE_ORDER.map((c) => <span key={c} className="key" title={COVERAGE_META[c].description}><i className={`sq cov-${c}`} /> {COVERAGE_META[c].text} <span className="num">{counts[c]}</span></span>)}
        </div>
      }>
      <div className="strip cov-strip" role="list" aria-label="Coverage of patient and context facts">
        {caseFacts.map((f) => {
          const cat: CoverageCategory = coverageCategory(f);
          return (
            <button key={f.id} type="button" role="listitem" className={`cov-${cat} ${ctx.highlight === f.id ? 'is-hl' : ''}`} title={`${factLabel(f.id, f)} — ${COVERAGE_META[cat].text}`} aria-label={`${factLabel(f.id, f)}: ${COVERAGE_META[cat].text}`}
              onMouseEnter={() => ctx.setHighlight(f.id)} onMouseLeave={() => ctx.setHighlight(null)} onFocus={() => ctx.setHighlight(f.id)} onBlur={() => ctx.setHighlight(null)} onClick={() => ctx.scrollToFact(f.id)} />
          );
        })}
      </div>
      <p className="small muted" style={{ margin: '8px 0 0' }}>
        {total ? <>{counts.cited + counts.referenced} of {total} facts were used ({Math.round(((counts.cited + counts.referenced) / total) * 100)}%); {counts.ignored} informative fact{counts.ignored === 1 ? '' : 's'} went unused.</> : 'No patient or context facts.'}
      </p>
    </Block>
  );
}
