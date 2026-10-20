import { useEffect, useMemo, useRef, useState, type ChangeEvent } from 'react';
import { useStore } from '../store';
import type { Lexicon, Section } from '../types';
import { describeError, lexiconLabel, titleFromDomain, type AnalyseRequest, type AnalyseResponse, type LexiconDisplay, type LexiconMeta } from '../lib/api';
import { useApi } from '../lib/useApiSettings';
import { analyseExport, buildSingleTraceBundle } from '../lib/analyseBundle';
import { buildAnalyseRequest, hasAnyDocument } from '../lib/documents';
import { downloadJson } from '../lib/download';
import { entityDisplay } from '../lib/format';
import { hrefTrace, navigate } from '../lib/router';
import { Banner, Chip } from '../components/Shared';
import { GroundingBody } from './GroundingView';
import { AnalysePage } from './AnalyseView';

/** The starter lexicon every service lists, and the matching trace packaged with the viewer. */
const EXAMPLE_LEXICON_ID = 'example:incident-triage';
const EXAMPLE_DOMAIN = 'incident-triage';
const EXAMPLE_TRACE_URL = './examples/incident-trace.json';
const FALLBACK_LEXICON: LexiconDisplay = { version: 'unknown', entities: [], findings: [] };

type Busy = 'idle' | 'example' | 'upload' | 'analyse';

export function AnalyseTraceView() {
  const api = useApi();
  const { setBundle } = useStore();
  const [lexicons, setLexicons] = useState<LexiconMeta[] | null>(null);
  const [lexiconId, setLexiconId] = useState('');
  const [lexicon, setLexicon] = useState<LexiconDisplay | null>(null);
  const [lexiconError, setLexiconError] = useState<string | null>(null);
  const [documents, setDocuments] = useState<Record<string, string>>({});
  const [reasoning, setReasoning] = useState('');
  const [answer, setAnswer] = useState('');
  const [entity, setEntity] = useState('');
  const [busy, setBusy] = useState<Busy>('idle');
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [result, setResult] = useState<{ req: AnalyseRequest; res: AnalyseResponse; at: string } | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  // The lexicons on the service (examples first, then the workspace's uploads); the chosen one's sections shape the form.
  useEffect(() => {
    let cancelled = false;
    api.lexicons().then((ls) => { if (!cancelled) { setLexicons(ls); setLexiconError(null); } }).catch((e) => { if (!cancelled) { setLexicons([]); setLexiconError(describeError(e)); } });
    return () => { cancelled = true; };
  }, [api]);
  useEffect(() => {
    let cancelled = false;
    setLexicon(null);
    if (!lexiconId) return;
    api.lexicon(lexiconId).then((l) => { if (!cancelled) { setLexicon(l); setLexiconError(null); } }).catch((e) => { if (!cancelled) setLexiconError(describeError(e)); });
    return () => { cancelled = true; };
  }, [api, lexiconId]);

  const examples = useMemo(() => (lexicons ?? []).filter((l) => l.source === 'example'), [lexicons]);
  const uploads = useMemo(() => (lexicons ?? []).filter((l) => l.source !== 'example'), [lexicons]);
  const meta = useMemo(() => lexicons?.find((l) => l.id === lexiconId) ?? null, [lexicons, lexiconId]);
  const sections: Section[] = useMemo(() => lexicon?.sections?.length ? lexicon.sections : meta?.sections ?? [], [lexicon, meta]);
  const domain = lexicon?.domain ?? meta?.domain ?? null;
  const inScope = useMemo(() => (lexicon?.entities ?? []).filter((e) => e.in_scope !== false), [lexicon]);
  const chosen = !!lexiconId;

  const built = useMemo(() => result ? buildSingleTraceBundle(result.req, result.res, lexicon ?? FALLBACK_LEXICON) : null, [result, lexicon]);
  const lex: Lexicon = built?.bundle.index.lexicon ?? { version: 'unknown', entities: [], findings: [] };

  const setDoc = (id: string, value: string) => setDocuments((d) => ({ ...d, [id]: value }));
  const chooseLexicon = (id: string) => { setLexiconId(id); setEntity(''); setResult(null); setError(null); };
  const clear = () => { setDocuments({}); setReasoning(''); setAnswer(''); setEntity(''); setResult(null); setError(null); setNotice(null); };

  const refreshLexicons = async (): Promise<LexiconMeta[]> => { const ls = await api.lexicons(); setLexicons(ls); return ls; };

  const onFile = async (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file) return;
    setBusy('upload'); setError(null); setNotice(null);
    try {
      const text = await file.text();
      const created = await api.uploadLexicon(text, file.name.replace(/\.json$/i, ''));
      const ls = await refreshLexicons();
      if (!ls.some((l) => l.id === created.id)) setLexicons([...ls, created]);
      chooseLexicon(created.id);
      setNotice(`Uploaded lexicon ${lexiconLabel(created)}: ${created.n_entities} categories, ${created.n_findings} findings, ${created.sections.length} document section${created.sections.length === 1 ? '' : 's'}.`);
    } catch (err) {
      setError(describeError(err));
    } finally { setBusy('idle'); }
  };

  /** Choose the incident-triage example lexicon from the service's list and fill the packaged example trace. */
  const loadExample = async () => {
    setBusy('example'); setError(null); setNotice(null);
    try {
      const list = lexicons ?? (await refreshLexicons());
      const target = list.find((l) => l.id === EXAMPLE_LEXICON_ID) ?? list.find((l) => l.source === 'example' && l.domain === EXAMPLE_DOMAIN) ?? null;
      if (!target) throw new Error(`This service lists no ${EXAMPLE_DOMAIN} example lexicon. Upload public/examples/lexicon-incident-triage.json with "Upload lexicon" and paste the example by hand.`);
      const tr = await fetch(EXAMPLE_TRACE_URL, { cache: 'no-cache' });
      if (!tr.ok) throw new Error(`HTTP ${tr.status} loading the example trace`);
      const example = (await tr.json()) as { documents: Record<string, string>; reasoning: string; answer: string };
      chooseLexicon(target.id);
      setDocuments({ ...example.documents });
      setReasoning(example.reasoning);
      setAnswer(example.answer);
      setNotice(`Loaded the ${titleFromDomain(target.domain).toLowerCase()} example on lexicon ${lexiconLabel(target)}: ${target.sections.map((s) => s.title).join(', ')}.`);
    } catch (e) {
      setError(describeError(e));
    } finally { setBusy('idle'); }
  };

  const analyse = async () => {
    setError(null); setNotice(null);
    if (!lexiconId) { setError('Choose a lexicon first; the document fields follow its sections.'); return; }
    if (!hasAnyDocument(documents)) { setError('Fill in at least one document; claims are graded against the documents.'); return; }
    if (!reasoning.trim()) { setError('Paste the model\'s reasoning before analysing.'); return; }
    if (!answer.trim()) { setError('Paste the model\'s final answer before analysing.'); return; }
    const req = buildAnalyseRequest({ documents, sections, reasoning, answer, entity: entity || undefined, lexiconId });
    setBusy('analyse'); setResult(null);
    try {
      const res = await api.analyse(req);
      setResult({ req, res, at: new Date().toISOString() });
    } catch (e) {
      setError(describeError(e));
    } finally { setBusy('idle'); }
  };

  const exportJson = () => {
    if (!result) return;
    downloadJson(`analyse-${result.res.case?.case_id ?? 'trace'}-${result.at.replace(/[:.]/g, '-')}.json`,
      analyseExport(result.req, result.res, { api_base: api.settings.base || 'same origin', lexicon_version: result.res.lexicon?.version ?? lexicon?.version ?? null, lexicon_id: lexiconId, domain: result.res.domain ?? domain, analysed_at: result.at }));
  };
  const openInViewer = () => {
    if (!built) return;
    setBundle(built.bundle);
    navigate(hrefTrace(built.traceKey, 'grounding'));
  };

  const g = result?.res.grounding ?? null;
  const parsed = result?.res.parsed_answer ?? null;
  const working = busy !== 'idle';
  const lexiconHelp = lexiconError ? `Lexicon unavailable: ${lexiconError}`
    : meta ? `${titleFromDomain(meta.domain)}, version ${meta.version}: ${meta.n_entities} categories, ${meta.n_findings} findings, ${meta.sections.length} document section${meta.sections.length === 1 ? '' : 's'}.`
      : lexicons && !lexicons.length ? 'This service lists no lexicons yet. Upload one to begin.'
        : 'The vocabulary the service grades against: its document sections, findings and answer categories. The service has no default.';

  return (
    <AnalysePage active="trace" title="Analyse a trace" wide lede="Choose the lexicon for your domain, then paste the documents the model saw, its reasoning and its final answer. The service grades every factual claim against the documents and draws the reasoning constellation. No model is called.">
      <form className="panel" aria-labelledby="analyse-form-title" onSubmit={(e) => { e.preventDefault(); void analyse(); }}>
        <div className="panel-head">
          <h2 id="analyse-form-title" style={{ margin: 0 }}>Inputs</h2>
          <div className="row small">
            <button type="button" className="btn small" onClick={() => void loadExample()} disabled={working || !lexicons}>{busy === 'example' ? 'Loading…' : 'Load example'}</button>
            <button type="button" className="btn small quiet" onClick={clear} disabled={working}>Clear</button>
          </div>
        </div>

        <div className="form-grid" style={{ marginBottom: 14 }}>
          <label className="field block">
            <span>Lexicon</span>
            <select value={lexiconId} onChange={(e) => chooseLexicon(e.target.value)} disabled={!lexicons} aria-describedby="lexicon-help" required>
              <option value="">{lexicons ? 'Choose a lexicon…' : 'Loading…'}</option>
              {examples.length > 0 && <optgroup label="Examples">{examples.map((l) => <option key={l.id} value={l.id}>{lexiconLabel(l)}</option>)}</optgroup>}
              {uploads.length > 0 && <optgroup label="Uploads">{uploads.map((l) => <option key={l.id} value={l.id}>{lexiconLabel(l)}</option>)}</optgroup>}
            </select>
            <span id="lexicon-help" className="muted">{lexiconHelp}</span>
          </label>
          <div className="field block">
            <span>Your own domain</span>
            <span className="row" style={{ gap: 8, minHeight: 34 }}>
              <button type="button" className="btn small" onClick={() => fileInput.current?.click()} disabled={working}>{busy === 'upload' ? 'Uploading…' : 'Upload lexicon'}</button>
              <input ref={fileInput} type="file" accept=".json,application/json" className="visually-hidden" aria-label="Choose a lexicon JSON file to upload" onChange={(e) => void onFile(e)} />
            </span>
            <span className="muted">A lexicon JSON file (version, domain, sections, entities, findings) is posted to the service and selected here; the document fields follow its sections. <code>public/examples/lexicon-incident-triage.json</code> is a template.</span>
          </div>
        </div>

        {chosen ? (
          <div className="form-grid">
            {sections.map((s) => (
              <label key={s.id} className="field block">
                <span>{s.title}</span>
                <textarea className="report" value={documents[s.id] ?? ''} onChange={(e) => setDoc(s.id, e.target.value)} spellCheck={false} placeholder="Leave empty if there is no such document" />
              </label>
            ))}
            {!sections.length && !lexiconError && <p className="muted">Loading the lexicon's document sections…</p>}
            <label className="field block">
              <span>Expected answer (optional)</span>
              <select value={entity} onChange={(e) => setEntity(e.target.value)} disabled={!lexicon} aria-describedby="entity-help">
                <option value="">Not stated</option>
                {inScope.map((e) => <option key={e.id} value={e.id}>{e.display}</option>)}
              </select>
              <span id="entity-help" className="muted">{lexicon ? 'The category the documents support, if known. Used to mark the model\'s answer correct or incorrect.' : lexiconError ? 'Lexicon unavailable.' : 'Loading the lexicon…'}</span>
            </label>
            <label className="field block full">
              <span>Reasoning</span>
              <textarea className="reasoning" value={reasoning} onChange={(e) => setReasoning(e.target.value)} spellCheck={false} placeholder="The model's reasoning text, as returned (up to 200 KB)" required />
            </label>
            <label className="field block full">
              <span>Answer</span>
              <textarea className="answer" value={answer} onChange={(e) => setAnswer(e.target.value)} spellCheck={false} placeholder={'Answer: …\nConfidence: …'} required />
            </label>
          </div>
        ) : (
          <p className="muted" style={{ margin: '4px 0 0' }}>Choose a lexicon, or press <strong>Load example</strong>, and the document fields for its sections appear here.</p>
        )}
        {error && <Banner tone="bad">{error}</Banner>}
        {notice && !error && <Banner tone="info">{notice}</Banner>}
        <div className="actions" style={{ marginTop: 12 }}>
          <button type="submit" className="btn primary" disabled={working || !chosen}>{busy === 'analyse' ? 'Analysing…' : 'Analyse'}</button>
          <span className="small muted">Sends the text to {api.settings.base || 'this origin'} at /api/analyse{lexiconId ? ` with lexicon ${lexiconId}` : ''}.</span>
        </div>
      </form>

      {result && built && (
        <section aria-labelledby="analyse-result-title" style={{ marginTop: 24 }}>
          <div className="panel-head">
            <h2 id="analyse-result-title" style={{ margin: 0 }}>Result</h2>
            <div className="row small">
              <button type="button" className="btn small" onClick={exportJson}>Export result JSON</button>
              <button type="button" className="btn small" onClick={openInViewer} title="Load this trace as a one-trace bundle and open the full trace views">Open in trace views</button>
            </div>
          </div>
          {result.res.oracle === 'extracted'
            ? <Banner tone="info">Oracle: extracted from the documents. No truth table was supplied, so each claim is graded against what the documents themselves state; findings no document mentions grade as unsupported.</Banner>
            : <Banner tone="info">Oracle: the supplied truth table.</Banner>}
          {result.res.warnings?.map((w) => <Banner key={w} tone="warn">{w}</Banner>)}
          <div className="row small" style={{ margin: '8px 0 12px' }} aria-label="Summary of the analysis">
            {(result.res.domain ?? domain) && <Chip tone="neutral">domain {result.res.domain ?? domain}</Chip>}
            <Chip tone="neutral">{built.trace.claims.length} claims</Chip>
            {!g && parsed?.entity && <Chip tone="neutral"><span className="entity">Parsed: {entityDisplay(lex, parsed.entity)}</span></Chip>}
            {parsed?.subtype && <Chip tone="neutral">subtype {parsed.subtype}</Chip>}
            {!g && parsed?.hedged && <Chip tone="warn" icon="≈">hedged</Chip>}
            {!entity && result.res.case?.entity && result.res.case.entity !== 'OTHER' && <Chip tone="neutral">expected answer taken from the documents: {entityDisplay(lex, result.res.case.entity)}</Chip>}
            {lexiconError && <Chip tone="warn" icon="!">lexicon unavailable, ids shown raw</Chip>}
          </div>
          <GroundingBody trace={built.trace} caseFile={built.caseFile} lexicon={lex} reportsTitle="Documents, as submitted" />
        </section>
      )}
    </AnalysePage>
  );
}
