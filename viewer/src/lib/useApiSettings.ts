import { useCallback, useMemo, useSyncExternalStore } from 'react';
import { createApi, loadApiSettings, saveApiSettings, type ApiClient, type ApiSettings } from './api';

// A tiny external store so every view sees the same API settings without threading them through the bundle store
// (they must survive bundle loads and resets, and never live in a URL).
let current: ApiSettings = loadApiSettings();
const listeners = new Set<() => void>();
const subscribe = (fn: () => void) => { listeners.add(fn); return () => { listeners.delete(fn); }; };
const get = () => current;

export function setApiSettings(next: Partial<ApiSettings>): void {
  current = { ...current, ...next };
  saveApiSettings(current);
  for (const fn of listeners) fn();
}

export function useApiSettings(): [ApiSettings, (next: Partial<ApiSettings>) => void] {
  const s = useSyncExternalStore(subscribe, get, get);
  const set = useCallback((next: Partial<ApiSettings>) => setApiSettings(next), []);
  return [s, set];
}

/** A client bound to the current settings; re-created when they change. */
export function useApi(): ApiClient {
  const [s] = useApiSettings();
  return useMemo(() => createApi(s), [s]);
}
