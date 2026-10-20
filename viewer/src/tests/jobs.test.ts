import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError, type Job, type JobStatus } from '../lib/api';
import { canCancel, estimateCalls, etaText, progressFraction, startJobPolling, type PollState } from '../lib/jobs';

function job(status: JobStatus, done = 0): Job {
  return { job_id: 'j', status, created: '2026-10-20T00:00:00Z', started: null, finished: null, progress: { done, total: 10, ok: done, errors: 0, eta_s: (10 - done) * 2 }, config: { mode: 'audit', client: { kind: 'sim' }, case_set: 'sample', efforts: ['low'], runs: 1 } };
}
const flush = async () => { for (let i = 0; i < 5; i++) await Promise.resolve(); };

describe('startJobPolling', () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it('polls every 3 s and stops on a terminal status', async () => {
    const sequence = [job('queued'), job('running', 3), job('running', 7), job('scoring', 10), job('done', 10), job('done', 10)];
    let i = 0;
    const fetchJob = vi.fn(async () => sequence[Math.min(i++, sequence.length - 1)]);
    const seen: PollState[] = [];
    const p = startJobPolling({ fetchJob, onChange: (s) => seen.push(s) });
    await flush();
    expect(fetchJob).toHaveBeenCalledTimes(1);
    expect(seen.at(-1)?.job?.status).toBe('queued');
    expect(seen.at(-1)?.polling).toBe(true);

    await vi.advanceTimersByTimeAsync(2999);
    expect(fetchJob).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(1);
    expect(fetchJob).toHaveBeenCalledTimes(2);
    expect(seen.at(-1)?.job?.progress?.done).toBe(3);

    await vi.advanceTimersByTimeAsync(3000 * 3);
    expect(fetchJob).toHaveBeenCalledTimes(5);
    expect(seen.at(-1)?.job?.status).toBe('done');
    expect(seen.at(-1)?.polling).toBe(false);
    expect(p.state().attempts).toBe(5);

    // Terminal: no further polls, however long we wait.
    await vi.advanceTimersByTimeAsync(60_000);
    expect(fetchJob).toHaveBeenCalledTimes(5);
  });

  it('keeps the last job through a transient failure and stops after a 404', async () => {
    const results: Array<Job | Error> = [job('running', 2), new TypeError('Failed to fetch'), job('running', 4), new ApiError(404, 'not_found', 'No job j')];
    let i = 0;
    const fetchJob = vi.fn(async () => { const r = results[Math.min(i++, results.length - 1)]; if (r instanceof Error) throw r; return r; });
    const seen: PollState[] = [];
    startJobPolling({ fetchJob, onChange: (s) => seen.push(s) });
    await flush();
    await vi.advanceTimersByTimeAsync(3000);
    expect(seen.at(-1)?.error).toMatch(/Could not reach the service/);
    expect(seen.at(-1)?.job?.progress?.done).toBe(2);
    expect(seen.at(-1)?.polling).toBe(true);
    await vi.advanceTimersByTimeAsync(3000);
    expect(seen.at(-1)?.error).toBeNull();
    expect(seen.at(-1)?.job?.progress?.done).toBe(4);
    await vi.advanceTimersByTimeAsync(3000);
    expect(seen.at(-1)?.error).toBe('No job j');
    expect(seen.at(-1)?.polling).toBe(false);
    await vi.advanceTimersByTimeAsync(30_000);
    expect(fetchJob).toHaveBeenCalledTimes(4);
  });

  it('stop() cancels the pending timer and refresh() polls at once', async () => {
    const fetchJob = vi.fn(async () => job('running', 1));
    const p = startJobPolling({ fetchJob, onChange: () => {} });
    await flush();
    expect(fetchJob).toHaveBeenCalledTimes(1);
    await p.refresh();
    expect(fetchJob).toHaveBeenCalledTimes(2);
    p.stop();
    expect(p.state().polling).toBe(false);
    await vi.advanceTimersByTimeAsync(30_000);
    expect(fetchJob).toHaveBeenCalledTimes(2);
  });

  it('honours a custom interval', async () => {
    const fetchJob = vi.fn(async () => job('queued'));
    startJobPolling({ fetchJob, onChange: () => {}, intervalMs: 500 });
    await flush();
    await vi.advanceTimersByTimeAsync(1500);
    expect(fetchJob).toHaveBeenCalledTimes(4);
  });
});

describe('job helpers', () => {
  it('computes progress, ETA, cancellability and the call estimate', () => {
    expect(progressFraction({ done: 5, total: 10 })).toBe(0.5);
    expect(progressFraction({ done: 5, total: 0 })).toBeNull();
    expect(progressFraction(null)).toBeNull();
    expect(etaText({ done: 0, total: 1, eta_s: 45 }, 'running')).toBe('about 45 s left');
    expect(etaText({ done: 0, total: 1, eta_s: 600 }, 'running')).toBe('about 10 min left');
    expect(etaText({ done: 0, total: 1, eta_s: 3900 }, 'running')).toBe('about 1 h 5 min left');
    expect(etaText({ done: 1, total: 1, eta_s: 0 }, 'done')).toBeNull();
    expect(etaText({ done: 1, total: 1, eta_s: null }, 'running')).toBeNull();
    expect(canCancel('queued')).toBe(true);
    expect(canCancel('running')).toBe(true);
    expect(canCancel('scoring')).toBe(false);
    expect(canCancel('done')).toBe(false);
    expect(estimateCalls({ n_cases: 6, n_perturbations: 30 }, 3, 2)).toBe(216);
    expect(estimateCalls(null, 3, 2)).toBe(0);
  });
});
