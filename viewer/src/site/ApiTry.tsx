import { useMemo, useState, type ReactNode } from 'react';
import { authHeaders } from '../lib/api';
import { useApiSettings } from '../lib/useApiSettings';
import { Code, prettyJson } from './Code';
import { apiOrigin, curlFor } from './examples';

export interface ApiResult { status: number; statusText: string; ms: number; bytes: number; json: unknown; text: string }

/** A live request sheet: method and path, an editable JSON body, the equivalent curl, and the response as sent back. */
export function ApiTry({ method, path, body, note, summary, sendLabel = 'Send', fetchImpl }: {
  method: 'GET' | 'POST' | 'DELETE';
  path: string;
  /** Initial request body (JSON text); editable in the sheet. */
  body?: string;
  note?: ReactNode;
  /** Renders a reading of a successful JSON response above the raw text. */
  summary?: (json: unknown, result: ApiResult) => ReactNode;
  sendLabel?: string;
  fetchImpl?: typeof fetch;
}) {
  const [settings] = useApiSettings();
  const [text, setText] = useState(body ?? '');
  const [pathText, setPathText] = useState(path);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<ApiResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showCurl, setShowCurl] = useState(false);
  const url = useMemo(() => apiOrigin(settings.base) + (pathText.startsWith('/') ? pathText : '/' + pathText), [settings.base, pathText]);
  const curl = useMemo(() => curlFor(method, url, method === 'GET' ? undefined : text || undefined, settings.token || undefined), [method, url, text, settings.token]);

  async function send() {
    setBusy(true); setError(null); setResult(null);
    const t0 = Date.now();
    try {
      if (method !== 'GET' && text.trim()) JSON.parse(text); // tell the visitor before the server does
      const f = fetchImpl ?? ((...a: Parameters<typeof fetch>) => fetch(...a));
      const res = await f(url, {
        method,
        headers: authHeaders(settings, method === 'GET' ? {} : { 'Content-Type': 'application/json' }),
        body: method === 'GET' ? undefined : text,
        cache: 'no-store',
      });
      const raw = await res.text();
      let json: unknown = null;
      try { json = raw ? JSON.parse(raw) : null; } catch { json = null; }
      setResult({ status: res.status, statusText: res.statusText, ms: Date.now() - t0, bytes: raw.length, json, text: raw });
    } catch (e) {
      setError(e instanceof SyntaxError ? `The body is not valid JSON: ${e.message}` : e instanceof Error ? e.message : String(e));
    } finally { setBusy(false); }
  }

  const pretty = result ? (result.json !== null ? prettyJson(result.json) : { text: result.text.slice(0, 60_000), truncated: result.text.length > 60_000 }) : null;
  const ok = result ? result.status >= 200 && result.status < 300 : false;
  return (
    <div className="request">
      <div className="req-head">
        <span className="method">{method}</span>
        {method === 'GET' ? (
          <input type="text" aria-label="Request path" value={pathText} onChange={(e) => setPathText(e.target.value)} style={{ flex: 1, minWidth: 220 }} />
        ) : <span className="path">{pathText}</span>}
        <span className="spacer" />
        <button type="button" className="btn small quiet" aria-pressed={showCurl} onClick={() => setShowCurl((v) => !v)}>curl</button>
      </div>
      <div className="req-body">
        {method !== 'GET' && <textarea aria-label="Request body (JSON)" value={text} onChange={(e) => setText(e.target.value)} spellCheck={false} />}
        {showCurl && <Code lang="shell">{curl}</Code>}
        <div className="req-foot">
          <button type="button" className="btn primary" disabled={busy} onClick={send}>{busy ? 'Sending' : sendLabel}</button>
          {note && <span className="note">{note}</span>}
          {error && <span className="note" role="alert" style={{ color: 'var(--contradicted)' }}>{error}</span>}
        </div>
      </div>
      {result && pretty && (
        <div className="response" aria-live="polite">
          <div className="res-head">
            <span className={`status ${ok ? 'ok' : 'bad'}`}>{result.status} {result.statusText || (ok ? 'OK' : '')}</span>
            <span className="muted small">{result.ms} ms, {formatBytes(result.bytes)}</span>
            <span className="muted small">{url}</span>
          </div>
          <div className="res-body">
            {ok && summary && result.json !== null && summary(result.json, result)}
            {ok && summary && result.json !== null ? (
              <details><summary>Raw response{pretty.truncated ? ' (first 60 KB)' : ''}</summary><pre>{pretty.text}</pre></details>
            ) : <pre>{pretty.text}</pre>}
          </div>
        </div>
      )}
    </div>
  );
}

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}
