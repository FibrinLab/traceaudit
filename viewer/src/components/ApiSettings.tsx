import { useEffect, useRef, useState } from 'react';
import { createApi, describeError, normaliseBase } from '../lib/api';
import { useApiSettings } from '../lib/useApiSettings';
import { Banner } from './Shared';

/** Gear button and dialog for the service connection: API base URL and bearer token (localStorage, never in URLs). */
export function ApiSettingsButton() {
  const [settings, setSettings] = useApiSettings();
  const ref = useRef<HTMLDialogElement>(null);
  const [open, setOpen] = useState(false);
  const [base, setBase] = useState(settings.base);
  const [token, setToken] = useState(settings.token);
  const [showToken, setShowToken] = useState(false);
  const [check, setCheck] = useState<{ tone: 'good' | 'bad' | 'info'; text: string } | null>(null);
  const [checking, setChecking] = useState(false);

  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) { setBase(settings.base); setToken(settings.token); setCheck(null); setShowToken(false); d.showModal?.(); }
    if (!open && d.open) d.close();
  }, [open, settings]);

  const save = () => { setSettings({ base: normaliseBase(base), token: token.trim() }); setOpen(false); };
  const test = async () => {
    setChecking(true); setCheck(null);
    try {
      const h = await createApi({ base: normaliseBase(base), token: token.trim() }).health();
      setCheck({ tone: 'good', text: `Connected: traceaudit ${h.version}, lexicon ${h.lexicon_version}, workspace ${h.workspace}, clients ${h.clients.join(', ') || 'none'}${h.operator_keys?.length ? `; the site's own key covers ${h.operator_keys.join(', ')}` : ''}.` });
    } catch (e) {
      setCheck({ tone: 'bad', text: describeError(e) });
    } finally { setChecking(false); }
  };

  return (
    <>
      <button type="button" className="btn small" onClick={() => setOpen(true)} aria-haspopup="dialog" title="Service settings">
        <span aria-hidden="true">⚙</span> Settings
      </button>
      <dialog ref={ref} onClose={() => setOpen(false)} aria-labelledby="api-settings-title">
        <h2 id="api-settings-title" style={{ marginTop: 0 }}>Service settings</h2>
        <p className="muted small">Where the Analyse tab sends requests. Both values stay in this browser's local storage and are never put in a URL.</p>
        <form className="stack" onSubmit={(e) => { e.preventDefault(); save(); }}>
          <label className="field block">
            <span>API base URL</span>
            <input type="text" value={base} onChange={(e) => setBase(e.target.value)} placeholder="Same origin (leave empty)" autoComplete="off" spellCheck={false} />
            <span className="muted">Leave empty when the viewer is served by <code>traceaudit serve</code>. Otherwise the service origin, for example <code>http://127.0.0.1:8080</code>.</span>
          </label>
          <label className="field block">
            <span>Bearer token</span>
            <span className="row" style={{ gap: 6 }}>
              <input type={showToken ? 'text' : 'password'} value={token} onChange={(e) => setToken(e.target.value)} autoComplete="off" style={{ flex: 1 }} aria-describedby="token-help" />
              <button type="button" className="btn small" aria-pressed={showToken} onClick={() => setShowToken((s) => !s)}>{showToken ? 'Hide' : 'Show'}</button>
            </span>
            <span id="token-help" className="muted">Optional. Maps to a workspace on the service; anonymous requests use the public workspace.</span>
          </label>
          {check && <Banner tone={check.tone}>{check.text}</Banner>}
          <div className="row between" style={{ marginTop: 8 }}>
            <button type="button" className="btn" onClick={() => void test()} disabled={checking}>{checking ? 'Checking…' : 'Check connection'}</button>
            <span className="row" style={{ gap: 8 }}>
              <button type="button" className="btn" onClick={() => setOpen(false)}>Cancel</button>
              <button type="submit" className="btn primary">Save</button>
            </span>
          </div>
        </form>
      </dialog>
    </>
  );
}
