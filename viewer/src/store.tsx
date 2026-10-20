import { createContext, useCallback, useContext, useEffect, useMemo, useReducer, useState, type ReactNode } from 'react';
import type { Bundle, CaseFile } from './types';
import { bundleUrlFromLocation, loadBundleFromUrl } from './lib/bundle';
import { settingsKey } from './lib/ratings';

export interface Settings {
  backendUrl: string;
  backendToken: string;
  theme: 'auto' | 'light' | 'dark';
  showLinkedMentions: boolean;
}

const DEFAULT_SETTINGS: Settings = { backendUrl: '', backendToken: '', theme: 'auto', showLinkedMentions: false };

export type Mode = 'explore' | 'rate' | 'review';

interface State {
  bundle: Bundle | null;
  status: 'idle' | 'loading' | 'ready' | 'error';
  error: string | null;
  /** The URL the current (or last requested) bundle was loaded from; null for files and in-memory bundles. */
  bundleUrl: string | null;
  settings: Settings;
  mode: Mode;
  /** Bumps whenever a case file finishes loading so consumers re-render. */
  caseVersion: number;
}

type Action =
  | { type: 'loading'; url?: string | null }
  | { type: 'loaded'; bundle: Bundle }
  | { type: 'error'; error: string }
  | { type: 'settings'; settings: Partial<Settings> }
  | { type: 'mode'; mode: Mode }
  | { type: 'caseLoaded' }
  | { type: 'reset' };

function reducer(state: State, action: Action): State {
  switch (action.type) {
    case 'loading': return { ...state, status: 'loading', error: null, bundleUrl: action.url === undefined ? state.bundleUrl : action.url };
    case 'loaded': return { ...state, status: 'ready', bundle: action.bundle, error: null, settings: loadSettings(action.bundle.index.run.run_id) };
    case 'error': return { ...state, status: 'error', error: action.error };
    case 'settings': {
      const settings = { ...state.settings, ...action.settings };
      if (state.bundle) saveSettings(state.bundle.index.run.run_id, settings);
      return { ...state, settings };
    }
    case 'mode': return { ...state, mode: action.mode };
    case 'caseLoaded': return { ...state, caseVersion: state.caseVersion + 1 };
    case 'reset': return { ...state, bundle: null, status: 'idle', error: null };
  }
}

function loadSettings(runId: string): Settings {
  try {
    const raw = localStorage.getItem(settingsKey(runId)) ?? localStorage.getItem('traceaudit:settings');
    return raw ? { ...DEFAULT_SETTINGS, ...(JSON.parse(raw) as Partial<Settings>) } : DEFAULT_SETTINGS;
  } catch { return DEFAULT_SETTINGS; }
}
function saveSettings(runId: string, s: Settings): void {
  try {
    localStorage.setItem(settingsKey(runId), JSON.stringify(s));
    localStorage.setItem('traceaudit:settings', JSON.stringify(s));
  } catch { /* storage unavailable */ }
}

interface StoreValue extends State {
  dispatch: (a: Action) => void;
  setBundle: (b: Bundle) => void;
  loadFromUrl: (url: string) => Promise<void>;
  /** Programmatic equivalent of opening the viewer with `?bundle=<url>`: records the URL and loads it,
   *  sending `headers` (e.g. the service bearer token) with every bundle request. Resolves true on success. */
  openBundle: (url: string, headers?: Record<string, string>) => Promise<boolean>;
  updateSettings: (s: Partial<Settings>) => void;
}

const StoreContext = createContext<StoreValue | null>(null);

export function StoreProvider({ children, autoload = true }: { children: ReactNode; autoload?: boolean }) {
  const [state, dispatch] = useReducer(reducer, { bundle: null, status: 'idle', error: null, bundleUrl: null, settings: DEFAULT_SETTINGS, mode: 'explore', caseVersion: 0 });

  const openBundle = useCallback(async (url: string, headers?: Record<string, string>): Promise<boolean> => {
    dispatch({ type: 'loading', url });
    try {
      const b = await loadBundleFromUrl(url, headers ? { headers } : {});
      dispatch({ type: 'loaded', bundle: b });
      return true;
    } catch (e) {
      dispatch({ type: 'error', error: e instanceof Error ? e.message : String(e) });
      return false;
    }
  }, []);
  const loadFromUrl = useCallback(async (url: string) => { await openBundle(url); }, [openBundle]);

  useEffect(() => {
    if (!autoload) return;
    if (window.location.protocol === 'file:') {
      // fetch() of local files is blocked in most browsers; show the picker instead.
      dispatch({ type: 'error', error: 'Opened from file:// — use the Load bundle panel to pick the exported folder or bundle.json.' });
      return;
    }
    void loadFromUrl(bundleUrlFromLocation());
  }, [autoload, loadFromUrl]);

  useEffect(() => {
    const t = state.settings.theme;
    document.documentElement.dataset.theme = t === 'auto' ? '' : t;
  }, [state.settings.theme]);

  const value = useMemo<StoreValue>(() => ({
    ...state,
    dispatch,
    setBundle: (b) => dispatch({ type: 'loaded', bundle: b }),
    loadFromUrl,
    openBundle,
    updateSettings: (s) => dispatch({ type: 'settings', settings: s }),
  }), [state, loadFromUrl, openBundle]);

  return <StoreContext.Provider value={value}>{children}</StoreContext.Provider>;
}

export function useStore(): StoreValue {
  const v = useContext(StoreContext);
  if (!v) throw new Error('useStore outside StoreProvider');
  return v;
}

/** Lazily load a case file; returns {caseFile, error, loading}. */
export function useCaseFile(caseId: string | null): { caseFile: CaseFile | null; error: string | null; loading: boolean } {
  const { bundle, dispatch } = useStore();
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const cached = caseId && bundle ? bundle.cases.get(caseId) ?? null : null;
  useEffect(() => {
    if (!bundle || !caseId || cached) return;
    let cancelled = false;
    setLoading(true); setError(null);
    bundle.loadCase(caseId)
      .then(() => { if (!cancelled) { setLoading(false); dispatch({ type: 'caseLoaded' }); } })
      .catch((e: unknown) => { if (!cancelled) { setLoading(false); setError(e instanceof Error ? e.message : String(e)); } });
    return () => { cancelled = true; };
  }, [bundle, caseId, cached, dispatch]);
  return { caseFile: cached, error, loading };
}

export function useTrace(traceKey: string | null) {
  const caseId = traceKey ? traceKey.split('|')[0] : null;
  const { caseFile, error, loading } = useCaseFile(caseId);
  const trace = useMemo(() => caseFile?.traces.find((t) => t.trace_key === traceKey) ?? null, [caseFile, traceKey]);
  return { caseFile, trace, error: error ?? (caseFile && !trace ? `Trace ${traceKey} not found in case ${caseId}` : null), loading };
}

declare const __VIEWER_VERSION__: string;
export const VIEWER_VERSION: string = typeof __VIEWER_VERSION__ !== 'undefined' ? __VIEWER_VERSION__ : '0.0.0-dev';
