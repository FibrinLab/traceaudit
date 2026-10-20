import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from 'react';
import { useStore, useTrace, VIEWER_VERSION } from '../store';
import { ReportPane } from '../components/ReportPane';
import { TracePane } from '../components/TracePane';
import { Banner, Chip, TraceHeader } from '../components/Shared';
import { hrefRate, navigate } from '../lib/router';
import { presentationOrder } from '../lib/shuffle';
import {
  RATER_ID_RE, emptyTraceRating, exportFilename, isComplete, loadRatingState, newSessionId, ratingRecords, saveRatingState, toggleTag, toJsonl,
  type DimensionId, type RatingState,
} from '../lib/ratings';
import { downloadText } from '../lib/download';
import { formatDuration } from '../lib/format';

const ACTIVE_RATER_KEY = 'traceaudit:active-rater';

export function RateView({ index }: { index: number | null }) {
  const { bundle } = useStore();
  const idx = bundle!.index;
  const study = idx.study;
  const runId = idx.run.run_id;
  const [state, setState] = useState<RatingState | null>(null);

  // Resume the active rater for this run from sessionStorage.
  useEffect(() => {
    if (!study) return;
    try {
      const active = sessionStorage.getItem(`${ACTIVE_RATER_KEY}:${runId}`);
      if (active) {
        const s = loadRatingState(localStorage, runId, study.study_id, active);
        if (s) setState(s);
      }
    } catch { /* ignore */ }
  }, [study, runId]);

  if (!study) {
    return (
      <div className="narrow">
        <h1>Rating mode</h1>
        <Banner tone="warn">This bundle has no <code>study</code> block, so rating mode is unavailable. Export with a study (<code>traceaudit export --study …</code>) to rate.</Banner>
      </div>
    );
  }

  if (!state) {
    return <SignIn studyId={study.study_id} onStart={(raterId) => {
      const existing = loadRatingState(localStorage, runId, study.study_id, raterId);
      const s: RatingState = existing ?? {
        session: { rater_id: raterId, study_id: study.study_id, session_id: newSessionId(), order: presentationOrder(study.rating_set, study.blinding_seed, raterId), started_at: new Date().toISOString() },
        ratings: {},
      };
      // New browser session id each time the rater signs in; the order stays fixed.
      if (existing) s.session.session_id = newSessionId();
      saveRatingState(localStorage, runId, s);
      try { sessionStorage.setItem(`${ACTIVE_RATER_KEY}:${runId}`, raterId); } catch { /* ignore */ }
      setState(s);
    }} />;
  }

  const total = state.session.order.length;
  if (index === null || index < 0 || index >= total) {
    const firstIncomplete = state.session.order.findIndex((k) => !isComplete(state.ratings[k]));
    return <Redirect to={hrefRate(firstIncomplete === -1 ? 0 : firstIncomplete)} />;
  }

  return <RatingPage state={state} setState={setState} index={index} runId={runId} onSignOut={() => { try { sessionStorage.removeItem(`${ACTIVE_RATER_KEY}:${runId}`); } catch { /* ignore */ } setState(null); }} />;
}

function Redirect({ to }: { to: string }) {
  useEffect(() => { navigate(to); }, [to]);
  return <p className="muted">Redirecting…</p>;
}

function SignIn({ studyId, onStart }: { studyId: string; onStart: (raterId: string) => void }) {
  const [rater, setRater] = useState('');
  const [err, setErr] = useState<string | null>(null);
  const submit = (e: FormEvent) => {
    e.preventDefault();
    const r = rater.trim().toUpperCase();
    if (!RATER_ID_RE.test(r)) { setErr('Rater id must be R followed by two digits, e.g. R01.'); return; }
    onStart(r);
  };
  return (
    <div className="narrow">
      <h1>Rating mode, sign in</h1>
      <p className="muted">Traces are presented blinded and in a rater-specific random order. Ratings are saved in this browser as you go and exported as JSONL when you finish.</p>
      <form className="panel" onSubmit={submit}>
        <div className="row">
          <label>Study <input type="text" value={studyId} readOnly aria-readonly="true" /></label>
          <label>Rater id <input type="text" value={rater} onChange={(e) => setRater(e.target.value)} pattern="R\d\d" placeholder="R01" autoComplete="off" required aria-describedby="rater-help" /></label>
          <button type="submit" className="btn primary">Start / resume</button>
        </div>
        <p id="rater-help" className="small muted">Use the id assigned by the study lead (pattern R00–R99), never a name.</p>
        {err && <Banner tone="warn">{err}</Banner>}
      </form>
    </div>
  );
}

function RatingPage({ state, setState, index, runId, onSignOut }: { state: RatingState; setState: (s: RatingState) => void; index: number; runId: string; onSignOut: () => void }) {
  const { bundle, settings, updateSettings } = useStore();
  const idx = bundle!.index;
  const traceKey = state.session.order[index];
  const { caseFile, trace, error, loading } = useTrace(traceKey);
  const total = state.session.order.length;
  const rating = state.ratings[traceKey];
  const complete = isComplete(rating);
  const [focusedDim, setFocusedDim] = useState<DimensionId | null>(null);
  const [uploadMsg, setUploadMsg] = useState<string | null>(null);
  const [live, setLive] = useState('');
  const liveTimer = useRef<number | undefined>(undefined);

  const update = useCallback((fn: (s: RatingState) => RatingState) => {
    const next = fn(state);
    saveRatingState(localStorage, runId, next);
    setState(next);
  }, [state, runId, setState]);

  // Ensure a rating record exists with started_at as soon as the trace is shown.
  useEffect(() => {
    if (!rating) update((s) => ({ ...s, ratings: { ...s.ratings, [traceKey]: emptyTraceRating(traceKey, index, new Date().toISOString()) } }));
  }, [rating, traceKey, index, update]);

  // Accumulate active time while this trace is on screen (5 s ticks, paused when hidden).
  useEffect(() => {
    const t = window.setInterval(() => {
      if (document.visibilityState !== 'visible') return;
      update((s) => {
        const r = s.ratings[traceKey]; if (!r) return s;
        return { ...s, ratings: { ...s.ratings, [traceKey]: { ...r, duration_ms: r.duration_ms + 5000 } } };
      });
    }, 5000);
    return () => window.clearInterval(t);
  }, [traceKey, update]);

  const setRating = (patch: Partial<NonNullable<typeof rating>>) => update((s) => {
    const r = s.ratings[traceKey] ?? emptyTraceRating(traceKey, index, new Date().toISOString());
    const next = { ...r, ...patch };
    next.submitted_at = isComplete(next) ? new Date().toISOString() : r.submitted_at;
    return { ...s, ratings: { ...s.ratings, [traceKey]: next } };
  });

  const announce = (msg: string) => { setLive(msg); window.clearTimeout(liveTimer.current); liveTimer.current = window.setTimeout(() => setLive(''), 1500); };

  // Keyboard: 1–4 scores the focused dimension; N next (when complete); P previous.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      const inText = t && (t.tagName === 'TEXTAREA' || (t.tagName === 'INPUT' && (t as HTMLInputElement).type === 'text'));
      if (inText) return;
      if (/^[1-4]$/.test(e.key) && focusedDim) {
        e.preventDefault();
        setRating({ scores: { ...(rating?.scores ?? {}), [focusedDim]: Number(e.key) } });
        const dim = idx.rubric.dimensions.find((d) => d.id === focusedDim);
        announce(`${focusedDim} ${dim?.name ?? ''} scored ${e.key}`);
        return;
      }
      if ((e.key === 'n' || e.key === 'N') && complete && index + 1 < total) navigate(hrefRate(index + 1));
      if ((e.key === 'p' || e.key === 'P') && index > 0) navigate(hrefRate(index - 1));
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  });

  const done = state.session.order.filter((k) => isComplete(state.ratings[k])).length;
  const elapsed = Object.values(state.ratings).reduce((a, r) => a + r.duration_ms, 0);

  const doExport = () => {
    const recs = ratingRecords(state, { viewer_version: VIEWER_VERSION, bundle_run_id: runId });
    downloadText(exportFilename(state.session.study_id, state.session.rater_id), toJsonl(recs), 'application/x-ndjson');
    announce(`Exported ${recs.length} records`);
  };
  const doUpload = async () => {
    const recs = ratingRecords(state, { viewer_version: VIEWER_VERSION, bundle_run_id: runId });
    try {
      const res = await fetch(settings.backendUrl.replace(/\/$/, '') + '/ratings', { method: 'POST', headers: { 'Content-Type': 'application/x-ndjson', ...(settings.backendToken ? { 'X-Study-Token': settings.backendToken } : {}) }, body: toJsonl(recs) });
      setUploadMsg(res.ok ? `Uploaded ${recs.length} records (${res.status}).` : `Upload failed: HTTP ${res.status}`);
    } catch (e) { setUploadMsg(`Upload failed: ${e instanceof Error ? e.message : String(e)}`); }
  };

  const reports = useMemo(() => caseFile && trace ? caseFile.variants[trace.variant]?.reports ?? caseFile.case.reports : null, [caseFile, trace]);

  return (
    <div>
      <div className="row" style={{ justifyContent: 'space-between' }}>
        <div>
          <h1 style={{ margin: 0 }}>Trace {index + 1} of {total}</h1>
          <div className="small muted">Rater {state.session.rater_id}, study {state.session.study_id}. {done} of {total} complete in {formatDuration(elapsed)}.</div>
        </div>
        <div className="row">
          <a className="btn" href={hrefRate(index - 1)} aria-disabled={index === 0} onClick={(e) => { if (index === 0) e.preventDefault(); }}>Previous <kbd>P</kbd></a>
          <a className="btn primary" href={hrefRate(index + 1)} aria-disabled={!complete || index + 1 >= total} onClick={(e) => { if (!complete || index + 1 >= total) e.preventDefault(); }} title={complete ? '' : 'Score all seven dimensions and choose at least one tag first'}>Next <kbd>N</kbd></a>
        </div>
      </div>
      <div className="progress" style={{ margin: '8px 0' }} role="progressbar" aria-valuemin={0} aria-valuemax={total} aria-valuenow={done} aria-label="Rating progress"><div style={{ width: `${(done / total) * 100}%` }} /></div>
      <div className="sr-live" aria-live="polite">{live}</div>

      {error && <Banner tone="bad">{error}</Banner>}
      {(loading || !trace || !reports) && !error && <p className="muted">Loading trace…</p>}

      {trace && reports && caseFile && (
        <div className="rate-layout">
          <div>
            <TraceHeader trace={trace} caseId="" blinded presentation={{ index, total }} />
            <h2 style={{ marginTop: 8 }}>Source documents</h2>
            <ReportPane reports={reports} sections={caseFile.case.sections} />
            <h2>Model reasoning</h2>
            <TracePane reasoning={trace.reasoning} plain ariaLabel="Model reasoning (unannotated)" />
            <h2>Model answer</h2>
            <div className="panel"><pre className="answer-text">{trace.answer || '(empty answer)'}</pre></div>
          </div>
          <div>
            <h2 style={{ marginTop: 0 }}>Rating</h2>
            <p className="small muted">Score each dimension 1–4 (press <kbd>1</kbd>–<kbd>4</kbd> while a dimension has focus). Anchors expand under each dimension.</p>
            {idx.rubric.dimensions.map((d) => {
              const did = d.id as DimensionId;
              const val = rating?.scores[did];
              return (
                <fieldset key={d.id} className="dim" onFocus={() => setFocusedDim(did)} aria-describedby={`${d.id}-anchors`}>
                  <legend>{d.id} {d.name}{typeof val === 'number' ? <span className="muted"> scored {val}</span> : null}</legend>
                  <div className="radio-row" role="radiogroup" aria-label={`${d.id} ${d.name}`}>
                    {[1, 2, 3, 4].map((v) => (
                      <label key={v} title={d.anchors[v - 1]}>
                        <input type="radio" name={`t${index}-${d.id}`} value={v} checked={val === v} onChange={() => setRating({ scores: { ...(rating?.scores ?? {}), [did]: v } })} />
                        {v}
                      </label>
                    ))}
                  </div>
                  <details id={`${d.id}-anchors`}>
                    <summary className="small muted">Anchors</summary>
                    <ol className="anchors">{d.anchors.map((a, i) => <li key={i}><strong>{i + 1}</strong> — {a}</li>)}</ol>
                  </details>
                </fieldset>
              );
            })}
            <fieldset className="dim">
              <legend>Error tags <span className="muted small">(choose all that apply; “No error identified” is exclusive)</span></legend>
              <div className="tags">
                {idx.rubric.error_tags.map((t) => (
                  <label key={t.id} title={t.definition}>
                    <input type="checkbox" checked={rating?.error_tags.includes(t.id) ?? false} onChange={() => setRating({ error_tags: toggleTag(rating?.error_tags ?? [], t.id) })} />
                    <span>{t.label}<br /><span className="small muted">{t.definition}</span></span>
                  </label>
                ))}
              </div>
            </fieldset>
            <label>Comment<br />
              <textarea value={rating?.comment ?? ''} onChange={(e) => setRating({ comment: e.target.value })} placeholder="Optional free text" />
            </label>
            <div className="row small" style={{ marginTop: 8 }}>
              {complete ? <Chip tone="good" icon="✓">complete{rating?.submitted_at ? ` at ${new Date(rating.submitted_at).toLocaleTimeString()}` : ''}</Chip> : <Chip tone="warn" icon="!">incomplete</Chip>}
              <span className="muted">Autosaved locally.</span>
            </div>

            <div className="panel" style={{ marginTop: 16 }}>
              <h3 style={{ marginTop: 0 }}>Export</h3>
              <div className="row">
                <button type="button" className="btn primary" onClick={doExport}>Export ratings (JSONL)</button>
                {settings.backendUrl && <button type="button" className="btn" onClick={() => void doUpload()}>Upload to backend</button>}
                <button type="button" className="btn" onClick={onSignOut}>Sign out</button>
              </div>
              {uploadMsg && <p className="small" role="status">{uploadMsg}</p>}
              <details style={{ marginTop: 8 }}>
                <summary className="small">Backend settings (optional)</summary>
                <div className="row small" style={{ marginTop: 6 }}>
                  <label>Backend URL <input type="url" value={settings.backendUrl} onChange={(e) => updateSettings({ backendUrl: e.target.value })} placeholder="http://host:8765" /></label>
                  <label>Study token <input type="text" value={settings.backendToken} onChange={(e) => updateSettings({ backendToken: e.target.value })} /></label>
                </div>
              </details>
              <p className="small muted" style={{ marginBottom: 0 }}>Exports only complete traces: one record per dimension plus a <code>tags</code> record, in the <code>ratings-schema.json</code> format. Stored under <code>localStorage</code> key <code>traceaudit:ratings:{runId}:{state.session.study_id}:{state.session.rater_id}</code>.</p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
