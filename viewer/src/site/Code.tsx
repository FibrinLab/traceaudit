import { useState } from 'react';

/** Copy text to the clipboard; false when the browser refuses (insecure context, permissions, tests). */
export async function copyText(text: string): Promise<boolean> {
  try {
    if (typeof navigator !== 'undefined' && navigator.clipboard?.writeText) { await navigator.clipboard.writeText(text); return true; }
  } catch { /* fall through */ }
  return false;
}

export function CopyButton({ text, label = 'Copy' }: { text: string; label?: string }) {
  const [state, setState] = useState<'idle' | 'ok' | 'fail'>('idle');
  return (
    <button type="button" className="btn small quiet copy" onClick={async () => {
      const ok = await copyText(text);
      setState(ok ? 'ok' : 'fail');
      window.setTimeout(() => setState('idle'), 1600);
    }}>{state === 'ok' ? 'Copied' : state === 'fail' ? 'Select and copy' : label}</button>
  );
}

/** A code block in the site's typewriter face with a copy button. `lang` is a small label, not syntax colouring. */
export function Code({ children, lang, copy = true }: { children: string; lang?: string; copy?: boolean }) {
  const text = children.replace(/^\n/, '').replace(/\n$/, '');
  return (
    <div className={`codeblock${copy ? ' inline-copy' : ''}`}>
      {lang && <span className="lang" aria-hidden="true">{lang}</span>}
      {copy && <CopyButton text={text} />}
      <pre><code>{text}</code></pre>
    </div>
  );
}

/** Pretty JSON for display, bounded so a large response cannot freeze the page. */
export function prettyJson(value: unknown, limit = 60_000): { text: string; truncated: boolean } {
  let text: string;
  try { text = JSON.stringify(value, null, 1) ?? String(value); } catch { text = String(value); }
  if (text.length > limit) return { text: text.slice(0, limit) + '\n…', truncated: true };
  return { text, truncated: false };
}
