import { useCallback, useEffect, useState } from 'react';
import { describeError, isTerminal, type JobStatus, type JobSummary, formatHeadline } from '../lib/api';
import { useApi } from '../lib/useApiSettings';
import { POLL_INTERVAL_MS, progressFraction, statusTone, STATUS_TEXT } from '../lib/jobs';
import { hrefJob } from '../lib/router';
import { Banner, Chip } from '../components/Shared';
import { AnalysePage } from './AnalyseView';

export function StatusChip({ status, large = false }: { status: JobStatus | string; large?: boolean }) {
  const { tone, icon } = statusTone(status);
  return <Chip tone={tone} icon={icon} className={large ? 'badge-lg' : ''}>{STATUS_TEXT[status as JobStatus] ?? status}</Chip>;
}

export function ProgressBar({ done, total, label, large = false }: { done: number; total: number; label: string; large?: boolean }) {
  const frac = progressFraction({ done, total });
  return (
    <div className={`progress${large ? ' lg' : ''}`} role="progressbar" aria-label={label} aria-valuemin={0} aria-valuemax={total || undefined} aria-valuenow={frac === null ? undefined : done} aria-valuetext={frac === null ? 'unknown' : `${done} of ${total}`}>
      <div style={{ width: `${(frac ?? 0) * 100}%` }} />
    </div>
  );
}

/** `#/jobs`: every job in the workspace; refreshes every few seconds while any job is still moving. */
export function JobsView() {
  const api = useApi();
  const [jobs, setJobs] = useState<JobSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    setRefreshing(true);
    try { setJobs(await api.listJobs()); setError(null); }
    catch (e) { setError(describeError(e)); }
    finally { setRefreshing(false); }
  }, [api]);

  useEffect(() => { void load(); }, [load]);
  const active = !!jobs?.some((j) => !isTerminal(j.status));
  useEffect(() => {
    if (!active) return;
    const t = window.setInterval(() => { void load(); }, POLL_INTERVAL_MS);
    return () => window.clearInterval(t);
  }, [active, load]);

  return (
    <AnalysePage active="jobs" title="Jobs" lede={`Audit jobs in ${api.settings.token ? 'your workspace' : 'the public workspace'}${api.settings.base ? ` on ${api.settings.base}` : ''}.${active ? ` Refreshing every ${POLL_INTERVAL_MS / 1000} s while a job is running.` : ''}`}>
      <div className="row between" style={{ marginBottom: 12 }}>
        <div className="row small">
          <a href="#/analyse/audit" className="btn primary">New audit</a>
          <button type="button" className="btn" onClick={() => void load()} disabled={refreshing}>{refreshing ? 'Refreshing…' : 'Refresh'}</button>
        </div>
        {jobs && <span className="small muted">{jobs.length} job{jobs.length === 1 ? '' : 's'}</span>}
      </div>
      {error && <Banner tone="bad">{error}</Banner>}
      {jobs && jobs.length === 0 && !error && <p className="muted">No jobs yet. Start one from <a href="#/analyse/audit">Audit a model</a>.</p>}
      {jobs && jobs.length > 0 && (
        <div className="table-scroll">
          <table className="data job-table">
            <thead>
              <tr><th>Job</th><th>Status</th><th>Progress</th><th>Created</th><th>Headline</th></tr>
            </thead>
            <tbody>
              {jobs.map((j) => {
                const p = j.progress;
                return (
                  <tr key={j.job_id}>
                    <td><a href={hrefJob(j.job_id)} className="mono">{j.job_id}</a></td>
                    <td><StatusChip status={j.status} /></td>
                    <td className="progress-cell">
                      {p && p.total > 0 ? (
                        <>
                          <div className="small num">{p.done} / {p.total}{p.errors ? <span className="muted">, {p.errors} error{p.errors === 1 ? '' : 's'}</span> : null}</div>
                          <ProgressBar done={p.done} total={p.total} label={`Progress of job ${j.job_id}`} />
                        </>
                      ) : <span className="muted small">—</span>}
                    </td>
                    <td className="small">{formatWhen(j.created)}</td>
                    <td className="small">{formatHeadline(j.headline ?? j.summary_headline) ?? <span className="muted">—</span>}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </AnalysePage>
  );
}

export function formatWhen(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString('en-GB', { dateStyle: 'medium', timeStyle: 'short' });
}
