import { useEffect, useState } from 'react';

export type Route =
  | { name: 'home' }
  | { name: 'cases' }
  | { name: 'case'; caseId: string }
  | { name: 'trace'; traceKey: string; view: 'grounding' | 'counterfactual' | 'authority' | 'map' }
  | { name: 'rate'; index: number | null }
  | { name: 'cohort' }
  | { name: 'review'; caseId: string }
  | { name: 'analyse'; page: 'chooser' | 'trace' | 'audit' | 'ledger' }
  | { name: 'jobs' }
  | { name: 'job'; jobId: string }
  | { name: 'docs'; slug: string; anchor: string | null }
  | { name: 'notfound'; path: string };

export function parseHash(hash: string): Route {
  const path = hash.replace(/^#/, '') || '/';
  const parts = path.split('/').filter(Boolean).map((p) => {
    try { return decodeURIComponent(p); } catch { return p; }
  });
  if (parts.length === 0) return { name: 'home' };
  switch (parts[0]) {
    case 'cases': return { name: 'cases' };
    case 'case': return parts[1] ? { name: 'case', caseId: parts[1] } : { name: 'cases' };
    case 'trace': {
      const view = parts[2];
      if (parts[1] && (view === 'grounding' || view === 'counterfactual' || view === 'authority' || view === 'map')) {
        return { name: 'trace', traceKey: parts[1], view };
      }
      if (parts[1]) return { name: 'trace', traceKey: parts[1], view: 'grounding' };
      return { name: 'notfound', path };
    }
    case 'rate': return { name: 'rate', index: parts[1] !== undefined && /^\d+$/.test(parts[1]) ? Number(parts[1]) : null };
    case 'cohort': return { name: 'cohort' };
    case 'review': return parts[1] ? { name: 'review', caseId: parts[1] } : { name: 'notfound', path };
    case 'analyse':
      if (!parts[1]) return { name: 'analyse', page: 'chooser' };
      if (parts[1] === 'trace' || parts[1] === 'audit' || parts[1] === 'ledger') return { name: 'analyse', page: parts[1] };
      return { name: 'notfound', path };
    case 'jobs': return parts[1] ? { name: 'job', jobId: parts[1] } : { name: 'jobs' };
    case 'docs': return { name: 'docs', slug: parts[1] ?? 'overview', anchor: parts[2] ?? null };
    default: return { name: 'notfound', path };
  }
}

export function hrefTrace(traceKey: string, view: 'grounding' | 'counterfactual' | 'authority' | 'map'): string {
  return `#/trace/${encodeURIComponent(traceKey)}/${view}`;
}
export function hrefCase(caseId: string): string { return `#/case/${encodeURIComponent(caseId)}`; }
export function hrefReview(caseId: string): string { return `#/review/${encodeURIComponent(caseId)}`; }
export function hrefRate(index: number): string { return `#/rate/${index}`; }
export function hrefJob(jobId: string): string { return `#/jobs/${encodeURIComponent(jobId)}`; }
/** A manual chapter, optionally a heading inside it: `#/docs/api/analyse`. */
export function hrefDocs(slug: string, anchor?: string): string { return anchor ? `#/docs/${slug}/${anchor}` : `#/docs/${slug}`; }

export function navigate(href: string): void {
  if (window.location.hash === href) return;
  window.location.hash = href;
}

export function useRoute(): Route {
  const [route, setRoute] = useState<Route>(() => parseHash(window.location.hash));
  useEffect(() => {
    const onChange = () => setRoute(parseHash(window.location.hash));
    window.addEventListener('hashchange', onChange);
    return () => window.removeEventListener('hashchange', onChange);
  }, []);
  return route;
}
