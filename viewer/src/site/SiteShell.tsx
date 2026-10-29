import type { ReactNode } from 'react';
import { useStore, VIEWER_VERSION } from '../store';
import { useHealth } from './useHealth';

export const REPO_URL = 'https://github.com/FibrinLab/traceaudit';

export function SiteShell({ active, children }: { active: 'home' | 'manual' | 'api'; children: ReactNode }) {
  const { settings, updateSettings } = useStore();
  const health = useHealth();
  return (
    <div className="site">
      <header className="masthead">
        <div className="sheet">
          <a className="brand" href="#/">traceaudit</a>
          <nav aria-label="Site">
            <a href="#/" aria-current={active === 'home' ? 'page' : undefined}>Overview</a>
            <a href="#/docs" aria-current={active === 'manual' ? 'page' : undefined}>Manual</a>
            <a href="#/docs/api" aria-current={active === 'api' ? 'page' : undefined}>API</a>
            <a href="#/analyse">Open the viewer</a>
            <a href={REPO_URL} rel="noreferrer">Source</a>
          </nav>
          <span className="spacer" />
          <div className="status" aria-live="polite">
            {health.status === 'ok' && <span className="live"><i aria-hidden="true" />service {health.health.version}, {health.ms} ms</span>}
            {health.status === 'down' && <span className="live down" title={health.error}><i aria-hidden="true" />service unreachable</span>}
            {health.status === 'loading' && <span className="live"><i aria-hidden="true" />checking the service</span>}
            <div className="seg" role="group" aria-label="Colour theme">
              {(['light', 'dark'] as const).map((t) => (
                <button key={t} type="button" aria-pressed={settings.theme === t} onClick={() => updateSettings({ theme: t })}>{t === 'light' ? 'Paper' : 'Ink'}</button>
              ))}
            </div>
          </div>
        </div>
      </header>
      {children}
      <footer className="colophon">
        <div className="sheet">
          <span>traceaudit {health.status === 'ok' ? health.health.version : VIEWER_VERSION}</span>
          <span>Apache-2.0</span>
          <a href={REPO_URL} rel="noreferrer">github.com/FibrinLab/traceaudit</a>
          <a href={`${REPO_URL}/tree/main/specs`} rel="noreferrer">Specifications</a>
          <a href="#/docs/limits">Research status and limits</a>
          <span>Standard-library Python.</span>
        </div>
      </footer>
    </div>
  );
}
