import { useEffect } from 'react';
import { navigate, useRoute, type Route } from './lib/router';
import { useApi } from './lib/useApiSettings';
import { useStore, VIEWER_VERSION } from './store';
import { LoadPanel } from './components/LoadPanel';
import { KeyboardHelp } from './components/Shared';
import { CasesView } from './views/CasesView';
import { CaseView } from './views/CaseView';
import { GroundingView } from './views/GroundingView';
import { CounterfactualView } from './views/CounterfactualView';
import { AuthorityView } from './views/AuthorityView';
import { MapView } from './views/MapView';
import { RateView } from './views/RateView';
import { CohortView } from './views/CohortView';
import { ReviewView } from './views/ReviewView';
import { AnalyseView } from './views/AnalyseView';
import { AnalyseTraceView } from './views/AnalyseTraceView';
import { AuditView } from './views/AuditView';
import { JobsView } from './views/JobsView';
import { JobView } from './views/JobView';
import { ApiSettingsButton } from './components/ApiSettings';

const GLOBAL_SHORTCUTS: Array<[string, string]> = [
  ['?', 'Toggle this help'],
  ['g c', 'Go to cases'],
  ['g o', 'Go to the cohort dashboard'],
  ['g r', 'Go to rating mode'],
  ['g a', 'Go to Analyse'],
  ['g j', 'Go to jobs'],
  ['↑ ↓ / ← →', 'Move between claims in a trace pane, or along edges in a constellation'],
  ['Enter / Space', 'Select the focused claim or node'],
  ['Escape', 'Clear the selection'],
  ['1–4', 'Rating mode: score the focused dimension'],
  ['N / P', 'Rating mode: next / previous trace'],
];

export function App() {
  const route = useRoute();
  const { bundle, status, error, dispatch, settings, updateSettings } = useStore();
  const isRate = route.name === 'rate';

  useEffect(() => {
    dispatch({ type: 'mode', mode: route.name === 'rate' ? 'rate' : route.name === 'review' ? 'review' : 'explore' });
  }, [route.name, dispatch]);

  useEffect(() => {
    let pendingG = false;
    let timer: number | undefined;
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.tagName === 'SELECT' || t.isContentEditable)) return;
      if (e.key === 'g' && !pendingG) { pendingG = true; timer = window.setTimeout(() => { pendingG = false; }, 800); return; }
      if (pendingG) {
        pendingG = false; window.clearTimeout(timer);
        if (e.key === 'c') window.location.hash = '#/cases';
        if (e.key === 'o') window.location.hash = '#/cohort';
        if (e.key === 'r') window.location.hash = '#/rate';
        if (e.key === 'a') window.location.hash = '#/analyse';
        if (e.key === 'j') window.location.hash = '#/jobs';
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  useEffect(() => { document.title = titleFor(route); window.scrollTo(0, 0); }, [route]);

  // Landing: with no bundle to show and a reachable service, the front page is Analyse. The Load bundle panel
  // stays one click away in the top bar (it navigates to #/cases, which is never redirected).
  const api = useApi();
  useEffect(() => {
    if (route.name !== 'home' || status !== 'error') return;
    let cancelled = false;
    api.health().then(() => { if (!cancelled && window.location.hash.replace(/^#\/?$/, '') === '') navigate('#/analyse'); }).catch(() => { /* no service: show the Load bundle panel */ });
    return () => { cancelled = true; };
  }, [route.name, status, api]);

  const manifest = bundle?.index.run.manifest;
  const model = manifest?.model as { tag?: string; effort_mechanism?: string } | undefined;
  const casesActive = route.name === 'cases' || route.name === 'case' || route.name === 'trace' || route.name === 'home' || route.name === 'review';
  // The service pages need no bundle; everything else waits for one.
  const serviceRoute = route.name === 'analyse' || route.name === 'jobs' || route.name === 'job';

  return (
    <div className="app">
      <header className="topbar">
        <a className="wordmark" href={isRate ? '#/rate' : '#/cases'}>traceaudit<span>Trace Viewer</span></a>
        <nav className="tabs" aria-label="Main">
          {!isRate && <a href="#/cases" aria-current={casesActive ? 'page' : undefined}>Cases</a>}
          {!isRate && <a href="#/cohort" aria-current={route.name === 'cohort' ? 'page' : undefined}>Cohort</a>}
          {!isRate && <a href="#/analyse" aria-current={serviceRoute ? 'page' : undefined}>Analyse</a>}
          {bundle?.index.study && <a href="#/rate" aria-current={isRate ? 'page' : undefined}>Rate</a>}
          {isRate && <a href="#/cases">Exit rating mode</a>}
        </nav>
        <span className="spacer" />
        <div className="tools">
          <div className="seg" role="group" aria-label="Colour theme">
            {(['auto', 'light', 'dark'] as const).map((t) => (
              <button key={t} type="button" aria-pressed={settings.theme === t} onClick={() => updateSettings({ theme: t })}>{t === 'auto' ? 'System' : t === 'light' ? 'Light' : 'Dark'}</button>
            ))}
          </div>
          <KeyboardHelp shortcuts={GLOBAL_SHORTCUTS} />
          {!isRate && <ApiSettingsButton />}
          <button type="button" className="btn small" onClick={() => { dispatch({ type: 'reset' }); if (serviceRoute) window.location.hash = '#/cases'; }} title="Load a different bundle">Load bundle</button>
        </div>
      </header>
      {bundle && status === 'ready' && !serviceRoute && (
        <div className="provenance" aria-label="Run provenance">
          <dl>
            <div><dt>Run</dt><dd className="mono">{bundle.index.run.run_id}</dd></div>
            {!isRate && <div><dt>Model</dt><dd>{String(model?.tag ?? 'unknown')}</dd></div>}
            {!isRate && model?.effort_mechanism && <div><dt>Reasoning</dt><dd>{String(model.effort_mechanism)}</dd></div>}
            <div><dt>Lexicon</dt><dd>{bundle.index.lexicon.version}</dd></div>
            {!isRate && <div><dt>Scoring</dt><dd>{bundle.index.summary.scoring.rule}, {bundle.index.summary.scoring.verifier} verifier</dd></div>}
            {!isRate && <div><dt>Cases</dt><dd>{bundle.index.cases.length}</dd></div>}
            {!isRate && <div><dt>Traces</dt><dd>{bundle.index.summary.counts.traces}</dd></div>}
            <div><dt>traceaudit</dt><dd>{String(manifest?.traceaudit_version ?? '—')}</dd></div>
            <div><dt>Viewer</dt><dd>{VIEWER_VERSION}</dd></div>
          </dl>
        </div>
      )}
      <main>
        {serviceRoute ? (
          <RouteView route={route} />
        ) : status !== 'ready' || !bundle ? (
          <div className="narrow">
            <LoadPanel status={status} error={error} />
          </div>
        ) : (
          <RouteView route={route} />
        )}
      </main>
    </div>
  );
}

function titleFor(route: Route): string {
  switch (route.name) {
    case 'cases': return 'Cases — traceaudit';
    case 'case': return `Case ${route.caseId} — traceaudit`;
    case 'trace': return `${route.view} ${route.traceKey} — traceaudit`;
    case 'rate': return 'Rating — traceaudit';
    case 'cohort': return 'Cohort — traceaudit';
    case 'review': return `Review ${route.caseId} — traceaudit`;
    case 'analyse': return route.page === 'trace' ? 'Analyse a trace — traceaudit' : route.page === 'audit' ? 'Audit a model — traceaudit' : 'Analyse — traceaudit';
    case 'jobs': return 'Jobs — traceaudit';
    case 'job': return `Job ${route.jobId} — traceaudit`;
    default: return 'traceaudit Trace Viewer';
  }
}

function RouteView({ route }: { route: Route }) {
  switch (route.name) {
    case 'home':
    case 'cases': return <CasesView />;
    case 'case': return <CaseView caseId={route.caseId} />;
    case 'trace':
      switch (route.view) {
        case 'grounding': return <GroundingView traceKey={route.traceKey} />;
        case 'counterfactual': return <CounterfactualView traceKey={route.traceKey} />;
        case 'authority': return <AuthorityView traceKey={route.traceKey} />;
        case 'map': return <MapView traceKey={route.traceKey} />;
      }
      return null;
    case 'rate': return <RateView index={route.index} />;
    case 'cohort': return <CohortView />;
    case 'review': return <ReviewView caseId={route.caseId} />;
    case 'analyse': return route.page === 'trace' ? <AnalyseTraceView /> : route.page === 'audit' ? <AuditView /> : <AnalyseView />;
    case 'jobs': return <JobsView />;
    case 'job': return <JobView jobId={route.jobId} />;
    case 'notfound': return <div className="narrow"><h1>Not found</h1><p className="muted">No view at <code>{route.path}</code>. <a href="#/cases">Go to cases</a>.</p></div>;
  }
}
