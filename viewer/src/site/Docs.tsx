import { useEffect } from 'react';
import { hrefDocs } from '../lib/router';
import { CHAPTERS, chapterBySlug } from './docs/index';
import { SiteShell } from './SiteShell';

/** `#/docs/:slug[/:anchor]`: the manual, one chapter at a time with a numbered contents rail. */
export function Docs({ slug, anchor }: { slug: string; anchor: string | null }) {
  const chapter = chapterBySlug(slug);
  useEffect(() => {
    if (!chapter) return;
    if (anchor) {
      const el = document.getElementById(anchor);
      if (el) { el.scrollIntoView({ block: 'start' }); return; }
    }
    window.scrollTo(0, 0);
  }, [slug, anchor, chapter]);
  const i = chapter ? CHAPTERS.indexOf(chapter) : -1;
  const prev = i > 0 ? CHAPTERS[i - 1] : null;
  const next = i >= 0 && i < CHAPTERS.length - 1 ? CHAPTERS[i + 1] : null;
  return (
    <SiteShell active={slug === 'api' ? 'api' : 'manual'}>
      <main className="sheet manual">
        <nav className="toc" aria-label="Manual contents">
          <ol>
            {CHAPTERS.map((c) => (
              <li key={c.slug}>
                <a href={hrefDocs(c.slug)} aria-current={c === chapter ? 'page' : undefined}><span className="n">{c.n}</span><span>{c.title}</span></a>
                {c === chapter && c.sections.length > 0 && (
                  <ol className="sub">{c.sections.map((s) => <li key={s.id}><a href={hrefDocs(c.slug, s.id)}>{s.title}</a></li>)}</ol>
                )}
              </li>
            ))}
          </ol>
        </nav>
        <article className="chapter">
          {chapter ? (
            <>
              <p className="chapter-no">Chapter {chapter.n}</p>
              <h1>{chapter.title}</h1>
              <p className="lede">{chapter.blurb}</p>
              <chapter.Component />
              <nav className="pager" aria-label="Chapters">
                {prev && <a href={hrefDocs(prev.slug)}><small>Previous</small>{prev.n}. {prev.title}</a>}
                {next && <a className="next" href={hrefDocs(next.slug)}><small>Next</small>{next.n}. {next.title}</a>}
              </nav>
            </>
          ) : (
            <>
              <h1>No such chapter</h1>
              <p className="muted">Nothing at <code>{slug}</code>. Pick a chapter from the contents.</p>
            </>
          )}
        </article>
      </main>
    </SiteShell>
  );
}
