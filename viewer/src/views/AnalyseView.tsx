import type { ReactNode } from 'react';
import { Chip } from '../components/Shared';

/** Sub-navigation shared by the Analyse pages and the jobs pages. */
export type AnalysePageId = 'chooser' | 'trace' | 'audit' | 'ledger' | 'jobs';
export function AnalyseNav({ active }: { active: AnalysePageId }) {
  const tabs: Array<[typeof active, string, string]> = [
    ['chooser', '#/analyse', 'Overview'],
    ['ledger', '#/analyse/ledger', 'Paste a trace'],
    ['trace', '#/analyse/trace', 'Documents and reasoning'],
    ['audit', '#/analyse/audit', 'Audit a model'],
    ['jobs', '#/jobs', 'Jobs'],
  ];
  return (
    <nav aria-label="Analyse pages" className="view-tabs" style={{ marginTop: 0 }}>
      {tabs.map(([id, href, label]) => <a key={id} href={href} aria-current={active === id ? 'page' : undefined}>{label}</a>)}
    </nav>
  );
}

export function AnalysePage({ active, title, lede, children, wide = false }: { active: AnalysePageId; title: string; lede?: ReactNode; children: ReactNode; wide?: boolean }) {
  return (
    <div className={wide ? '' : 'narrow'}>
      <AnalyseNav active={active} />
      <h1>{title}</h1>
      {lede && <p className="lede">{lede}</p>}
      {children}
    </div>
  );
}

/** `#/analyse`: choose between the three modes of the service. */
export function AnalyseView() {
  return (
    <AnalysePage active="chooser" title="Does the reasoning hold up?" lede="traceaudit grades every factual claim in a model's reasoning against the source documents it was given, then checks whether its answer changes when the documents do. Any domain: bring your own lexicon.">
      <div className="choice-cards">
        <a className="choice-card" href="#/analyse/ledger">
          <h2>Paste a reasoning trace</h2>
          <p>Copy the engine's trace page, or choose its file. Every citation is checked against its fact and the 24 checks run.</p>
          <div className="calls"><Chip tone="good" icon="✓">Calls no model</Chip> <span className="small muted">Start here with an engine trace.</span></div>
        </a>
        <a className="choice-card" href="#/analyse/trace">
          <h2>Analyse documents and reasoning</h2>
          <p>Paste the source documents, the reasoning and the answer as plain text; each claim is graded against the documents with a lexicon.</p>
          <div className="calls"><Chip tone="good" icon="✓">Calls no model</Chip> <span className="small muted">For traces without fact ids.</span></div>
        </a>
        <a className="choice-card" href="#/analyse/audit">
          <h2>Audit a model</h2>
          <p>Run a case set through a model and get a scored bundle for the Cohort and Cases tabs.</p>
          <div className="calls"><Chip tone="warn" icon="!">Calls a model</Chip> <span className="small muted">On this site's key where offered, otherwise yours; the form shows the estimate first.</span></div>
        </a>
      </div>
      <p className="small muted" style={{ marginTop: 16 }}>Jobs you start are listed under <a href="#/jobs">Jobs</a>. The service address and token are set with Settings in the top bar; a bundle you already have opens with Load bundle.</p>
    </AnalysePage>
  );
}
