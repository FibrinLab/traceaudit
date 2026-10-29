import { useEffect, useState } from 'react';
import type { Health } from '../lib/api';
import { useApi } from '../lib/useApiSettings';

export type HealthState = { status: 'loading' } | { status: 'ok'; health: Health; ms: number } | { status: 'down'; error: string };

// One request per API base, shared by the masthead and the hero so the page asks the service once.
const cache = new Map<string, Promise<HealthState>>();

export function useHealth(): HealthState {
  const api = useApi();
  const [state, setState] = useState<HealthState>({ status: 'loading' });
  useEffect(() => {
    const key = api.settings.base;
    let p = cache.get(key);
    if (!p) {
      const t0 = Date.now();
      p = api.health().then((health) => ({ status: 'ok', health, ms: Date.now() - t0 } as HealthState))
        .catch((e: unknown) => ({ status: 'down', error: e instanceof Error ? e.message : String(e) } as HealthState));
      cache.set(key, p);
    }
    let live = true;
    p.then((s) => { if (live) setState(s); });
    return () => { live = false; };
  }, [api]);
  return state;
}

/** For tests: forget cached answers. */
export function resetHealthCache(): void { cache.clear(); }
