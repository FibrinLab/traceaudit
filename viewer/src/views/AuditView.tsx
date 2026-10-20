import { useEffect, useMemo, useState } from 'react';
import { budgetRemaining, defaultClientKind, describeError, type CaseSet, type Health, type JobCreate } from '../lib/api';
import { useApi } from '../lib/useApiSettings';
import { estimateCalls } from '../lib/jobs';
import { hrefJob, navigate } from '../lib/router';
import { Banner, Chip } from '../components/Shared';
import { AnalysePage } from './AnalyseView';

const EFFORTS = ['low', 'medium', 'high'] as const;

const CLIENT_HELP: Record<string, string> = {
  sim: 'The built-in simulated model. No endpoint or key; useful for trying the pipeline.',
  ollama: 'A local Ollama server. Endpoint is its base URL, for example http://127.0.0.1:11434; no key.',
  openai: 'An OpenAI-compatible chat completions endpoint. Leave the endpoint empty for api.openai.com.',
  anthropic: 'The Anthropic Messages API. Leave the endpoint empty for api.anthropic.com.',
};

const n = (v: number) => v.toLocaleString('en-GB');

export function AuditView() {
  const api = useApi();
  const [health, setHealth] = useState<Health | null>(null);
  const [caseSets, setCaseSets] = useState<CaseSet[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [caseSet, setCaseSet] = useState('');
  const [kind, setKind] = useState('');
  const [endpoint, setEndpoint] = useState('');
  const [model, setModel] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [efforts, setEfforts] = useState<Set<string>>(new Set(['medium']));
  const [runs, setRuns] = useState(1);
  const [notes, setNotes] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoadError(null);
    Promise.all([api.health(), api.caseSets()]).then(([h, sets]) => {
      if (cancelled) return;
      setHealth(h); setCaseSets(sets);
      setKind((k) => k || defaultClientKind(h));
      setCaseSet((c) => c || sets.find((s) => s.approved)?.id || '');
    }).catch((e) => { if (!cancelled) setLoadError(describeError(e)); });
    return () => { cancelled = true; };
  }, [api]);

  const selectedSet = useMemo(() => caseSets?.find((s) => s.id === caseSet) ?? null, [caseSets, caseSet]);
  const calls = estimateCalls(selectedSet, efforts.size, runs);
  const needsModel = kind !== 'sim';
  const onSiteKey = !!health?.operator_keys?.includes(kind);
  const needsKey = needsModel && kind !== 'ollama' && !onSiteKey;
  const limits = health?.limits ?? null;
  const remaining = budgetRemaining(health);
  /** Why the job cannot start on the site's key, if it cannot. */
  const limitProblem: string | null = !onSiteKey || !limits || !selectedSet ? null
    : calls > limits.max_calls_per_job
      ? `This job would make about ${n(calls)} model calls; the site allows ${n(limits.max_calls_per_job)} per job on its key. Choose fewer efforts or runs${selectedSet.n_cases + selectedSet.n_perturbations > limits.max_calls_per_job ? ', or a smaller case set' : ''}.`
      : remaining !== null && calls > remaining
        ? `This job would make about ${n(calls)} model calls, but only ${n(remaining)} remain in today's budget on the site's key. Choose fewer efforts or runs, or try again tomorrow.`
        : null;
  const toggleEffort = (e: string) => setEfforts((s) => { const next = new Set(s); if (next.has(e)) next.delete(e); else next.add(e); return next; });

  const submit = async () => {
    setError(null);
    if (!selectedSet) { setError('Choose a case set.'); return; }
    if (!selectedSet.approved) { setError(`${selectedSet.name} has not been approved for audit runs.`); return; }
    if (!kind) { setError('Choose a client kind.'); return; }
    if (needsModel && !model.trim()) { setError('Enter the model name or tag to call.'); return; }
    if (efforts.size === 0) { setError('Tick at least one effort level.'); return; }
    if (runs < 1 || runs > 5) { setError('Runs must be between 1 and 5.'); return; }
    if (limitProblem) { setError(limitProblem); return; }
    const req: JobCreate = {
      mode: 'audit',
      client: { kind, model: model.trim() || (kind === 'sim' ? 'simulated' : ''), ...(endpoint.trim() ? { endpoint: endpoint.trim() } : {}), ...(needsKey && apiKey ? { api_key: apiKey } : {}) },
      case_set: selectedSet.id,
      efforts: EFFORTS.filter((e) => efforts.has(e)),
      runs,
      ...(notes.trim() ? { notes: notes.trim() } : {}),
    };
    setSubmitting(true);
    try {
      const { job_id } = await api.createJob(req);
      setApiKey('');
      navigate(hrefJob(job_id));
    } catch (e) {
      setApiKey('');
      setError(describeError(e));
    } finally { setSubmitting(false); }
  };

  const callsText = selectedSet ? `(${selectedSet.n_cases} cases + ${selectedSet.n_perturbations} perturbations) × ${efforts.size} effort${efforts.size === 1 ? '' : 's'} × ${runs} run${runs === 1 ? '' : 's'}` : '';
  const minutes = calls ? `${Math.max(1, Math.round(calls * 4 / 60))} to ${Math.max(1, Math.round(calls * 12 / 60))} minutes` : 'a while';

  return (
    <AnalysePage active="audit" title="Audit a model" lede="Run every case and perturbation of a case set through a model, score the traces and export a bundle for the Cohort and Cases tabs. Where this site offers its own key, the job runs on it; otherwise it runs on yours.">
      {loadError && <Banner tone="bad">Could not load the service's case sets and client kinds: {loadError}</Banner>}
      <form className="panel" onSubmit={(e) => { e.preventDefault(); void submit(); }} aria-labelledby="audit-form-title">
        <h2 id="audit-form-title" style={{ marginTop: 0 }}>Job</h2>
        <div className="form-grid">
          <label className="field block full">
            <span>Case set</span>
            <select value={caseSet} onChange={(e) => setCaseSet(e.target.value)} disabled={!caseSets} required>
              {!caseSets && <option value="">{loadError ? 'Not available' : 'Loading…'}</option>}
              {caseSets?.length === 0 && <option value="">No case sets on this service</option>}
              {caseSets?.map((s) => (
                <option key={s.id} value={s.id} disabled={!s.approved}>
                  {s.name} ({s.n_cases} cases, {s.n_perturbations} perturbations){s.approved ? '' : ' — not approved'}
                </option>
              ))}
            </select>
            {selectedSet && (
              <span className="row small" style={{ gap: 8 }}>
                <Chip tone="neutral">{selectedSet.n_cases} cases</Chip>
                <Chip tone="neutral">{selectedSet.n_perturbations} perturbations</Chip>
                {selectedSet.approved ? <Chip tone="good" icon="✓">approved</Chip> : <Chip tone="warn" icon="!">not approved</Chip>}
                {(selectedSet.domain ?? health?.domain) && <Chip tone="neutral">domain {selectedSet.domain ?? health?.domain}</Chip>}
                <span className="muted">source: {selectedSet.source}</span>
              </span>
            )}
          </label>
          <label className="field block">
            <span>Client kind</span>
            <select value={kind} onChange={(e) => setKind(e.target.value)} disabled={!health} required>
              {!health && <option value="">{loadError ? 'Not available' : 'Loading…'}</option>}
              {health?.clients.map((c) => <option key={c} value={c}>{c}{health.operator_keys?.includes(c) ? ' (site key)' : ''}</option>)}
            </select>
            <span className="muted">{CLIENT_HELP[kind] ?? (health ? 'Allowed by this service.' : '')}</span>
          </label>
          <label className="field block">
            <span>Endpoint {kind === 'sim' ? '(not used)' : '(optional)'}</span>
            <input type="text" value={endpoint} onChange={(e) => setEndpoint(e.target.value)} placeholder={kind === 'ollama' ? 'http://127.0.0.1:11434' : 'Provider default'} disabled={kind === 'sim'} autoComplete="off" spellCheck={false} />
          </label>
          <label className="field block">
            <span>Model {needsModel ? '' : '(not used)'}</span>
            <input type="text" value={model} onChange={(e) => setModel(e.target.value)} placeholder={kind === 'ollama' ? 'llama3.1:8b' : 'model name or tag'} disabled={!needsModel} required={needsModel} autoComplete="off" spellCheck={false} />
          </label>
          {onSiteKey ? (
            <div className="field block" role="group" aria-label="API key">
              <span>API key</span>
              <span className="row" style={{ gap: 8, minHeight: 34 }}>
                <Chip tone="good" icon="✓">Runs on this site's key</Chip>
                {remaining !== null && limits && <span className="muted small">{n(remaining)} of {n(limits.max_calls_per_day)} calls left today; up to {n(limits.max_calls_per_job)} per job.</span>}
              </span>
              <span className="muted">No key to enter. The site pays for and rate-limits these calls.</span>
            </div>
          ) : (
            <label className="field block">
              <span>API key {needsKey ? '' : '(not used)'}</span>
              <input type="password" value={apiKey} onChange={(e) => setApiKey(e.target.value)} disabled={!needsKey} autoComplete="off" aria-describedby="key-help" />
              <span id="key-help" className="muted">Held in the service's memory for the job only; never written to disk, never shown again, cleared from this form on submit.</span>
            </label>
          )}
          <fieldset className="field block" style={{ border: 0, padding: 0, margin: 0 }}>
            <legend style={{ padding: 0, fontSize: 'var(--fs-0)' }}>Efforts</legend>
            <div className="checks">
              {EFFORTS.map((e) => (
                <label key={e} className="inline"><input type="checkbox" checked={efforts.has(e)} onChange={() => toggleEffort(e)} /> {e}</label>
              ))}
            </div>
          </fieldset>
          <label className="field block">
            <span>Runs per variant</span>
            <input type="number" min={1} max={5} value={runs} onChange={(e) => setRuns(Math.max(1, Math.min(5, Number(e.target.value) || 1)))} style={{ width: 90 }} />
            <span className="muted">1 to 5 samples at each effort.</span>
          </label>
          <label className="field block full">
            <span>Notes (optional)</span>
            <textarea value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Recorded in the run manifest" style={{ minHeight: 60 }} />
          </label>
        </div>

        {selectedSet && !limitProblem && (
          <Banner tone={kind === 'sim' ? 'info' : onSiteKey ? 'info' : 'warn'}>
            {kind === 'sim'
              ? <>The simulated client makes about <strong>{n(calls)}</strong> in-process calls ({callsText}). No external model is called.</>
              : onSiteKey
                ? <>About <strong>{n(calls)}</strong> model calls on this site's key: {callsText}. {remaining !== null && <>That leaves {n(Math.max(0, remaining - calls))} in today's budget. </>}Expect {minutes}; you can cancel from the job page, and traces already written are kept and scored.</>
                : <>Your model will be called about <strong>{n(calls)}</strong> times: {callsText}. Every call is billed to your key and the job runs for as long as those calls take; at a few seconds each, expect {minutes}. You can cancel from the job page; traces already written are kept and scored.</>}
          </Banner>
        )}
        {limitProblem && <Banner tone="warn">{limitProblem}</Banner>}
        {error && <Banner tone="bad">{error}</Banner>}
        <div className="actions" style={{ marginTop: 12 }}>
          <button type="submit" className="btn primary" disabled={submitting || !caseSets || !health || !!limitProblem}>{submitting ? 'Starting…' : 'Start audit'}</button>
          <a href="#/jobs" className="btn">View jobs</a>
        </div>
      </form>
    </AnalysePage>
  );
}
