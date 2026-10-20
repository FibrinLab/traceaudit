import { createContext, useCallback, useContext, useEffect, useMemo, useReducer, useState, type ReactNode } from 'react';
import type { Bundle, CaseFile } from './types';
import { bundleUrlFromLocation, loadBundleFromUrl } from './lib/bundle';
import { settingsKey } from './lib/ratings';

export interface Settings {
  backendUrl: string;
  backendToken: string;
  /** Light is the default. "auto" follows the operating system; it is never chosen for the user. */
  theme: 'auto' | 'light' | 'dark';
  showLinkedMentions: boolean;
}

const DEFAULT_SETTINGS: Settings = { backendUrl: '', backendToken: '', theme: 'light', showLinkedMentions: false };
const GLOBAL_SETTINGS_KEY = 'traceaudit:settings';

export type Mode = 'explore' | 'rate' | 'review';

/** idle: nothing requested (the Analyse pages are the landing); pick: the user asked to load a bundle (the Load
 *  bundle panel is shown); loading / ready / error follow a requested bundle. */
export type Status = 'idle' | 'pick' | 'loading' | 'ready' | 'error';

interface State {
  bundle: Bundle | null;
  status: Status;
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
  /** Drop the bundle and show the Load bundle panel. */
  | { type: 'reset' }
  /** Drop the bundle and the panel: back to the no-results state. */
  | { type: 'idle' };

function reducer(state: State, action: Action): State {
  switch (action.type) {
    case 'loading': return { ...state, status: 'loading', error: null, bundleUrl: action.url === undefined ? state.bundleUrl : action.url };
    case 'loaded': return { ...state, status: 'ready', bundle: action.bundle, error: null, settings: loadSettings(action.bundle.index.run.run_id) };
    case 'error': return { ...state, status: 'error', error: action.error };
    case 'settings': {
      const settings = { ...state.settings, ...action.settings };
      saveSettings(state.bundle?.index.run.run_id ?? null, settings);
      return { ...state, settings };
    }
    case 'mode': return { ...state, mode: action.mode };
    case 'caseLoaded': return { ...state, caseVersion: state.caseVersion + 1 };
    case 'reset': return { ...state, bundle: null, status: 'pick', error: null };
    case 'idle': return { ...state, bundle: null, status: 'idle', error: null };
  }
}

function parseSettings(raw: string | null): Settings | null {
  if (!raw) return null;
  try { return { ...DEFAULT_SETTINGS, ...(JSON.parse(raw) as Partial<Settings>) }; } catch { return null; }
}
/** Settings before any bundle is loaded: the last ones saved in this browser, else the defaults (light theme). */
function initialSettings(): Settings {
  try { return parseSettings(localStorage.getItem(GLOBAL_SETTINGS_KEY)) ?? DEFAULT_SETTINGS; } catch { return DEFAULT_SETTINGS; }
}
function loadSettings(runId: string): Settings {
  try { return parseSettings(localStorage.getItem(settingsKey(runId))) ?? parseSettings(localStorage.getItem(GLOBAL_SETTINGS_KEY)) ?? DEFAULT_SETTINGS; } catch { return DEFAULT_SETTINGS; }
}
function saveSettings(runId: string | null, s: Settings): void {
  try {
    if (runId) localStorage.setItem(settingsKey(runId), JSON.stringify(s));
    localStorage.setItem(GLOBAL_SETTINGS_KEY, JSON.stringify(s));
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
  const [state, dispatch] = useReducer(reducer, undefined, () => ({ bundle: null, status: 'idle' as Status, error: null, bundleUrl: null, settings: initialSettings(), mode: 'explore' as Mode, caseVersion: 0 }));

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

  // Only a `?bundle=<url>` on the address loads anything at start; otherwise the viewer opens on Analyse with no results.
  useEffect(() => {
    if (!autoload) return;
    const url = bundleUrlFromLocation();
    if (!url) return;
    if (window.location.protocol === 'file:') {
      // fetch() of local files is blocked in most browsers; show the picker instead.
      dispatch({ type: 'error', error: 'Opened from file:// — use the Load bundle panel to pick the exported folder or bundle.json.' });
      return;
    }
    void loadFromUrl(url);
  }, [autoload, loadFromUrl]);

  // The theme is always resolved to light or dark on <html>, so the stylesheet never guesses: "System" follows the OS.
  useEffect(() => {
    const t = state.settings.theme;
    const root = document.documentElement;
    if (t !== 'auto') { root.dataset.theme = t; return; }
    const mq = typeof window.matchMedia === 'function' ? window.matchMedia('(prefers-color-scheme: dark)') : null;
    const apply = () => { root.dataset.theme = mq?.matches ? 'dark' : 'light'; };
    apply();
    mq?.addEventListener?.('change', apply);
    return () => mq?.removeEventListener?.('change', apply);
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
