import { useEffect } from 'react';
import { useRoute, type Route } from './lib/router';
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
import { AnalyseLedgerView } from './views/AnalyseLedgerView';
import { JobsView } from './views/JobsView';
import { JobView } from './views/JobView';
import { ApiSettingsButton } from './components/ApiSettings';
import { Landing } from './site/Landing';
import { Docs } from './site/Docs';

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

  useEffect(() => {
    document.title = titleFor(route);
    // A manual deep link scrolls to its heading itself; everything else starts at the top.
    if (!(route.name === 'docs' && route.anchor)) window.scrollTo(0, 0);
  }, [route]);

  // The front page and the manual have their own chrome. `#/` with a bundle loading or loaded (`?bundle=`) is Cases.
  const siteRoute = route.name === 'docs' || (route.name === 'home' && status === 'idle');
  if (siteRoute) {
    return route.name === 'docs' ? <Docs slug={route.slug} anchor={route.anchor} /> : <Landing />;
  }

  const manifest = bundle?.index.run.manifest;
  const model = manifest?.model as { tag?: string; effort_mechanism?: string } | undefined;
  const casesActive = route.name === 'cases' || route.name === 'case' || route.name === 'trace' || route.name === 'home' || route.name === 'review';
  // The service pages need no bundle; everything else waits for one.
  const serviceRoute = route.name === 'analyse' || route.name === 'jobs' || route.name === 'job';

  return (
    <div className="app">
      <header className="topbar">
        <a className="wordmark" href={isRate ? '#/rate' : '#/analyse'}>traceaudit<span>Trace Viewer</span></a>
        <nav className="tabs" aria-label="Main">
          {!isRate && <a href="#/analyse" aria-current={serviceRoute ? 'page' : undefined}>Analyse</a>}
          {!isRate && <a href="#/cases" aria-current={casesActive ? 'page' : undefined}>Cases</a>}
          {!isRate && <a href="#/cohort" aria-current={route.name === 'cohort' ? 'page' : undefined}>Cohort</a>}
          {bundle?.index.study && <a href="#/rate" aria-current={isRate ? 'page' : undefined}>Rate</a>}
          {isRate && <a href="#/cases">Exit rating mode</a>}
        </nav>
        <span className="spacer" />
        <div className="tools">
          <div className="seg" role="group" aria-label="Colour theme">
            {(['light', 'dark', 'auto'] as const).map((t) => (
              <button key={t} type="button" aria-pressed={settings.theme === t} onClick={() => updateSettings({ theme: t })}>{t === 'auto' ? 'System' : t === 'light' ? 'Light' : 'Dark'}</button>
            ))}
          </div>
          <KeyboardHelp shortcuts={GLOBAL_SHORTCUTS} />
          {!isRate && <ApiSettingsButton />}
          <button type="button" className="btn small" onClick={() => { dispatch({ type: 'reset' }); if (serviceRoute) window.location.hash = '#/cases'; }} title={bundle ? 'Load a different bundle' : 'Load a bundle'}>Load bundle</button>
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
        ) : status === 'ready' && bundle ? (
          <RouteView route={route} />
        ) : status === 'idle' ? (
          <NoResults route={route} onLoad={() => dispatch({ type: 'reset' })} />
        ) : (
          <div className="narrow">
            <LoadPanel status={status} error={error} />
          </div>
        )}
      </main>
    </div>
  );
}

/** The bundle pages before any results exist: point at the two ways to get some. */
function NoResults({ route, onLoad }: { route: Route; onLoad: () => void }) {
  const title = route.name === 'cohort' ? 'Cohort' : route.name === 'rate' ? 'Rating mode' : route.name === 'review' ? 'Case review' : 'Cases';
  return (
    <div className="empty-state" role="status">
      <h1>{title}</h1>
      <p>No results loaded. Run an audit under Analyse, or load a bundle.</p>
      <div className="actions">
        <a className="btn primary" href="#/analyse/audit">Run an audit</a>
        <a className="btn" href="#/analyse/trace">Analyse a trace</a>
        <button type="button" className="btn" onClick={onLoad}>Load a bundle</button>
      </div>
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
    case 'analyse': return route.page === 'trace' ? 'Analyse a trace — traceaudit' : route.page === 'audit' ? 'Audit a model — traceaudit' : route.page === 'ledger' ? 'Fact ledger — traceaudit' : 'Analyse — traceaudit';
    case 'jobs': return 'Jobs — traceaudit';
    case 'job': return `Job ${route.jobId} — traceaudit`;
    case 'docs': return 'Manual — traceaudit';
    case 'home': return 'traceaudit';
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
    case 'analyse': return route.page === 'trace' ? <AnalyseTraceView /> : route.page === 'audit' ? <AuditView /> : route.page === 'ledger' ? <AnalyseLedgerView /> : <AnalyseView />;
    case 'jobs': return <JobsView />;
    case 'job': return <JobView jobId={route.jobId} />;
    case 'docs': return <Docs slug={route.slug} anchor={route.anchor} />;
    case 'notfound': return <div className="narrow"><h1>Not found</h1><p className="muted">No view at <code>{route.path}</code>. <a href="#/analyse">Go to Analyse</a>.</p></div>;
  }
}
