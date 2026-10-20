// Job polling state machine (spec 17 §5): poll every few seconds until a terminal status, then stop.
// Timers are the globals so tests can drive it with fake timers.
import { describeError, isTerminal, type Job, type JobProgress, type JobStatus } from './api';

export interface PollState {
  job: Job | null;
  /** Last error message, kept while polling continues (a transient failure should not blank the page). */
  error: string | null;
  /** True between start and the terminal status (or stop()). */
  polling: boolean;
  /** Completed fetches, successful or not. */
  attempts: number;
}

export interface PollerOptions {
  fetchJob: () => Promise<Job>;
  onChange: (s: PollState) => void;
  intervalMs?: number;
  /** Stop after this many consecutive failures (404 once is final: the job does not exist). */
  maxConsecutiveErrors?: number;
}

export interface Poller { stop: () => void; refresh: () => Promise<void>; state: () => PollState }

export const POLL_INTERVAL_MS = 3000;

export function startJobPolling(opts: PollerOptions): Poller {
  const interval = opts.intervalMs ?? POLL_INTERVAL_MS;
  const maxErrors = opts.maxConsecutiveErrors ?? 5;
  let state: PollState = { job: null, error: null, polling: true, attempts: 0 };
  let timer: ReturnType<typeof setTimeout> | null = null;
  let stopped = false;
  let inflight: Promise<void> | null = null;
  let consecutiveErrors = 0;

  const emit = (patch: Partial<PollState>) => { state = { ...state, ...patch }; opts.onChange(state); };
  const schedule = () => { if (!stopped) timer = setTimeout(() => { timer = null; void tick(); }, interval); };

  const tick = async (): Promise<void> => {
    if (stopped) return;
    if (inflight) return inflight;
    inflight = (async () => {
      try {
        const job = await opts.fetchJob();
        consecutiveErrors = 0;
        if (stopped) return;
        const terminal = isTerminal(job.status);
        emit({ job, error: null, attempts: state.attempts + 1, polling: !terminal });
        if (terminal) { stopped = true; return; }
      } catch (e) {
        consecutiveErrors += 1;
        if (stopped) return;
        const notFound = typeof e === 'object' && e !== null && 'status' in e && (e as { status: unknown }).status === 404;
        const giveUp = notFound || consecutiveErrors >= maxErrors;
        emit({ error: describeError(e), attempts: state.attempts + 1, polling: !giveUp });
        if (giveUp) { stopped = true; return; }
      } finally {
        inflight = null;
      }
      schedule();
    })();
    return inflight;
  };

  void tick();
  return {
    stop: () => { stopped = true; if (timer) { clearTimeout(timer); timer = null; } if (state.polling) emit({ polling: false }); },
    refresh: () => { if (timer) { clearTimeout(timer); timer = null; } return tick(); },
    state: () => state,
  };
}

/** Fraction done in [0, 1], or null when the total is unknown. */
export function progressFraction(p: JobProgress | null | undefined): number | null {
  if (!p || !p.total) return null;
  return Math.max(0, Math.min(1, p.done / p.total));
}

export function etaText(p: JobProgress | null | undefined, status: JobStatus | string): string | null {
  if (isTerminal(status)) return null;
  const s = p?.eta_s;
  if (s == null || !Number.isFinite(s)) return null;
  if (s < 60) return `about ${Math.max(1, Math.round(s))} s left`;
  const min = Math.round(s / 60);
  if (min < 60) return `about ${min} min left`;
  return `about ${Math.floor(min / 60)} h ${min % 60} min left`;
}

export const STATUS_TEXT: Record<JobStatus, string> = {
  queued: 'queued',
  running: 'running',
  scoring: 'scoring',
  exporting: 'exporting',
  done: 'done',
  failed: 'failed',
  cancelled: 'cancelled',
  interrupted: 'interrupted',
};

export function statusTone(status: JobStatus | string): { tone: string; icon: string } {
  switch (status) {
    case 'done': return { tone: 'good', icon: '✓' };
    case 'failed': return { tone: 'bad', icon: '✗' };
    case 'cancelled': return { tone: 'warn', icon: '–' };
    case 'interrupted': return { tone: 'warn', icon: '!' };
    case 'running': case 'scoring': case 'exporting': return { tone: 'knowledge', icon: '▶' };
    default: return { tone: 'neutral', icon: '·' };
  }
}

export function canCancel(status: JobStatus | string): boolean { return status === 'queued' || status === 'running'; }

/** Roughly how many model calls an audit job makes: every case and every perturbation, per effort, per run. */
export function estimateCalls(set: { n_cases: number; n_perturbations: number } | null, efforts: number, runs: number): number {
  if (!set) return 0;
  return (set.n_cases + set.n_perturbations) * Math.max(0, efforts) * Math.max(0, runs);
}
