import { useRef, useState, type ChangeEvent } from 'react';
import { useStore } from '../store';
import { bundleUrlFromLocation, loadBundleFromDirectoryHandle, loadBundleFromFiles } from '../lib/bundle';
import { Banner } from './Shared';

export function LoadPanel({ status, error }: { status: string; error: string | null }) {
  const { setBundle, loadFromUrl, dispatch, bundleUrl } = useStore();
  const [url, setUrl] = useState(bundleUrl ?? bundleUrlFromLocation());
  const [localError, setLocalError] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const dirInput = useRef<HTMLInputElement>(null);
  const hasFsAccess = typeof window !== 'undefined' && 'showDirectoryPicker' in window;

  const onFiles = async (e: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? []);
    if (!files.length) return;
    setLocalError(null);
    dispatch({ type: 'loading' });
    try {
      setBundle(await loadBundleFromFiles(files));
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setLocalError(msg);
      dispatch({ type: 'error', error: msg });
    } finally {
      e.target.value = '';
    }
  };

  const pickDirectory = async () => {
    try {
      const picker = (window as unknown as { showDirectoryPicker: () => Promise<FileSystemDirectoryHandle> }).showDirectoryPicker;
      const handle = await picker();
      dispatch({ type: 'loading' });
      setBundle(await loadBundleFromDirectoryHandle(handle));
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') return;
      const msg = err instanceof Error ? err.message : String(err);
      setLocalError(msg);
      dispatch({ type: 'error', error: msg });
    }
  };

  return (
    <div className="panel" aria-labelledby="load-title">
      <h1 id="load-title">Load bundle</h1>
      <p className="muted">
        Load a bundle exported by <code>traceaudit export</code>: a folder containing <code>index.json</code> and <code>cases/</code>, or a single <code>bundle.json</code>.
        Nothing leaves this browser. Without a bundle you can still <a href="#/analyse">analyse a trace or audit a model</a> through the service.
      </p>
      {status === 'loading' && <p role="status" aria-live="polite">Loading…</p>}
      {(error || localError) && status !== 'loading' && <Banner tone="warn">{localError ?? error}</Banner>}

      <h2>From a URL</h2>
      <form className="row" onSubmit={(e) => { e.preventDefault(); void loadFromUrl(url); }}>
        <label>Bundle directory or bundle.json{' '}
          <input type="text" value={url} onChange={(e) => setUrl(e.target.value)} size={40} aria-describedby="url-help" />
        </label>
        <button type="submit" className="btn primary">Load</button>
      </form>
      <p id="url-help" className="small muted">Relative to this page. You can also open the viewer with <code>?bundle=&lt;relative-url&gt;</code>. The packaged demo lives at <code>./demo/</code>.</p>

      <h2>From your computer</h2>
      <div className="row">
        {hasFsAccess && <button type="button" className="btn" onClick={() => void pickDirectory()}>Pick folder (Chromium)</button>}
        <button type="button" className="btn" onClick={() => dirInput.current?.click()}>Select folder contents</button>
        <button type="button" className="btn" onClick={() => fileInput.current?.click()}>Select bundle.json</button>
        <input ref={dirInput} type="file" multiple className="visually-hidden" aria-label="Select the exported bundle folder" onChange={onFiles}
          // @ts-expect-error non-standard but widely supported
          webkitdirectory="" directory="" />
        <input ref={fileInput} type="file" accept=".json,application/json" className="visually-hidden" aria-label="Select a single bundle.json file" onChange={onFiles} />
      </div>
    </div>
  );
}
