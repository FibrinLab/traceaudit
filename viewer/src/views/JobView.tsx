import { useEffect, useRef, useState } from 'react';
import { useStore } from '../store';
import { describeError, isTerminal, JOB_FILES, type Job, type JobFile, formatHeadline } from '../lib/api';
import { useApi } from '../lib/useApiSettings';
import { canCancel, etaText, startJobPolling, type PollState, type Poller } from '../lib/jobs';
import { downloadBlob } from '../lib/download';
import { navigate } from '../lib/router';
import { Banner, Loading } from '../components/Shared';
import { AnalysePage } from './AnalyseView';
import { formatWhen, ProgressBar, StatusChip } from './JobsView';

const FILE_TEXT: Record<JobFile, string> = {
  'summary.json': 'summary.json: the headline rates and intervals',
  'report.md': 'report.md: the written report',
  'traces.jsonl': 'traces.jsonl: every trace with its claims and scores',
  'long.csv': 'long.csv: one row per trace per metric, for analysis',
  'manifest.json': 'manifest.json: provenance of the run',
};

/** `#/jobs/:id`: polls the job every 3 s until it reaches a terminal status. */
export function JobView({ jobId }: { jobId: string }) {
  const api = useApi();
  const { openBundle } = useStore();
  const [state, setState] = useState<PollState>({ job: null, error: null, polling: true, attempts: 0 });
  const poller = useRef<Poller | null>(null);
  const [action, setAction] = useState<'idle' | 'cancel' | 'open' | 'resume' | JobFile>('idle');
  const [actionError, setActionError] = useState<string | null>(null);
  const [resumeKey, setResumeKey] = useState('');

  useEffect(() => {
    setState({ job: null, error: null, polling: true, attempts: 0 });
    const p = startJobPolling({ fetchJob: () => api.getJob(jobId), onChange: setState });
    poller.current = p;
    return () => { p.stop(); poller.current = null; };
  }, [api, jobId]);

  const job = state.job;
  const cancel = async () => {
    setAction('cancel'); setActionError(null);
    try { await api.cancelJob(jobId); await poller.current?.refresh(); }
    catch (e) { setActionError(describeError(e)); }
    finally { setAction('idle'); }
  };
  const openResults = async () => {
    setAction('open'); setActionError(null);
    const ok = await openBundle(api.bundleUrl(jobId), api.settings.token ? api.headers() : undefined);
    setAction('idle');
    if (ok) navigate('#/cohort');
    else setActionError('The bundle could not be loaded; the Load bundle panel shows the reason.');
  };
  const resume = async () => {
    setAction('resume'); setActionError(null);
    try { await api.resumeJob(jobId, resumeKey || undefined); setResumeKey(''); restartPolling(); }
    catch (e) { setResumeKey(''); setActionError(describeError(e)); }
    finally { setAction('idle'); }
  };
  const restartPolling = () => {
    poller.current?.stop();
    poller.current = startJobPolling({ fetchJob: () => api.getJob(jobId), onChange: setState });
  };
  const download = async (name: JobFile) => {
    setAction(name); setActionError(null);
    try { downloadBlob(`${jobId}-${name}`, await api.fetchFile(jobId, name)); }
    catch (e) { setActionError(describeError(e)); }
    finally { setAction('idle'); }
  };

  const p = job?.progress ?? null;
  const eta = job ? etaText(p, job.status) : null;
  const total = p?.total ?? 0;

  return (
    <AnalysePage active="jobs" title={`Job ${jobId}`} lede={<><a href="#/jobs">All jobs</a>{job && <> · created {formatWhen(job.created)}{job.started && <>, started {formatWhen(job.started)}</>}{job.finished && <>, finished {formatWhen(job.finished)}</>}</>}</>}>
      {state.error && (!job || state.polling) && <Banner tone={job ? 'warn' : 'bad'}>{job ? `Last poll failed, retrying: ${state.error}` : state.error}</Banner>}
      {state.error && job && !state.polling && !isTerminal(job.status) && <Banner tone="bad">Stopped polling after repeated failures: {state.error}. <button type="button" className="btn small" onClick={restartPolling}>Try again</button></Banner>}
      {!job && !state.error && <Loading what={`job ${jobId}`} />}
      {job && (
        <>
          <div className="panel" aria-live="polite">
            <div className="row" style={{ gap: 16, alignItems: 'center' }}>
              <StatusChip status={job.status} large />
              {p && total > 0 && <span className="hero-number" style={{ fontSize: 'var(--fs-4)' }}>{p.done}<span className="muted" style={{ fontSize: 'var(--fs-2)', fontWeight: 400 }}> / {total}</span></span>}
              <span className="small muted">
                {p ? <>{p.ok != null && <>{p.ok} ok</>}{p.errors ? <>, <span style={{ color: p.errors ? 'var(--contradicted)' : undefined }}>{p.errors} error{p.errors === 1 ? '' : 's'}</span></> : p.ok != null ? ', no errors' : null}{eta && <>, {eta}</>}</> : 'No progress reported yet'}
                {state.polling && <> · polling every 3 s</>}
              </span>
            </div>
            {p && total > 0 && <div style={{ marginTop: 10 }}><ProgressBar done={p.done} total={total} label="Job progress" large /></div>}
            {formatHeadline(job.headline) && <p style={{ marginTop: 12, marginBottom: 0 }}>{formatHeadline(job.headline)}</p>}
            {job.error && <Banner tone="bad">{job.error}</Banner>}
            {job.status === 'interrupted' && (
              <form className="row" style={{ marginTop: 12 }} onSubmit={(e) => { e.preventDefault(); void resume(); }}>
                <label className="field">
                  <span>API key to resume (if the client needs one)</span>
                  <input type="password" value={resumeKey} onChange={(e) => setResumeKey(e.target.value)} autoComplete="off" />
                </label>
                <button type="submit" className="btn" disabled={action !== 'idle'}>{action === 'resume' ? 'Resuming…' : 'Resume job'}</button>
              </form>
            )}
            {actionError && <Banner tone="bad">{actionError}</Banner>}
            <div className="actions" style={{ marginTop: 14 }}>
              {canCancel(job.status) && <button type="button" className="btn" onClick={() => void cancel()} disabled={action !== 'idle'}>{action === 'cancel' ? 'Cancelling…' : 'Cancel job'}</button>}
              {job.status === 'done' && <button type="button" className="btn primary" onClick={() => void openResults()} disabled={action !== 'idle'}>{action === 'open' ? 'Opening…' : 'Open results'}</button>}
              {job.status === 'done' && <span className="small muted">Loads the job's bundle and opens the Cohort dashboard.</span>}
            </div>
          </div>

          {job.status === 'done' && (
            <div className="panel" style={{ marginTop: 16 }}>
              <h2 style={{ marginTop: 0 }}>Downloads</h2>
              <ul className="stack" style={{ listStyle: 'none', padding: 0, margin: 0 }}>
                {JOB_FILES.map((name) => (
                  <li key={name} className="row" style={{ gap: 10 }}>
                    {api.settings.token
                      ? <button type="button" className="btn small" onClick={() => void download(name)} disabled={action !== 'idle'}>{action === name ? 'Fetching…' : 'Download'}</button>
                      : <a className="btn small" href={api.fileUrl(jobId, name)} download={`${jobId}-${name}`}>Download</a>}
                    <span className="small">{FILE_TEXT[name]}</span>
                  </li>
                ))}
              </ul>
              <p className="small muted" style={{ marginTop: 10 }}>Bundle URL for <code>?bundle=</code>: <code>{api.bundleUrl(jobId)}</code></p>
            </div>
          )}

          <div className="panel" style={{ marginTop: 16 }}>
            <h2 style={{ marginTop: 0 }}>Configuration</h2>
            <ConfigList job={job} />
          </div>
        </>
      )}
    </AnalysePage>
  );
}

function ConfigList({ job }: { job: Job }) {
  const c = job.config;
  const rows: Array<[string, string]> = [
    ['Mode', c.mode],
    ['Client', c.client?.kind ?? '—'],
    ['Model', c.client?.model ?? '—'],
    ['Endpoint', c.client?.endpoint ?? 'provider default'],
    ['Case set', c.case_set],
    ['Efforts', (c.efforts ?? []).join(', ') || '—'],
    ['Runs', String(c.runs ?? '—')],
  ];
  if (c.rule) rows.push(['Rule', c.rule]);
  if (c.seed != null) rows.push(['Seed', String(c.seed)]);
  if (c.notes) rows.push(['Notes', c.notes]);
  return (
    <dl className="kv">
      {rows.map(([k, v]) => <div key={k} style={{ display: 'contents' }}><dt>{k}</dt><dd>{v}</dd></div>)}
    </dl>
  );
}
