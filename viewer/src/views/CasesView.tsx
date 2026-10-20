import { useMemo, useState } from 'react';
import { useStore } from '../store';
import { hrefCase, hrefReview } from '../lib/router';
import { entityDisplay } from '../lib/format';
import { Chip } from '../components/Shared';
import { entityColor } from '../lib/palette';

export function CasesView() {
  const { bundle } = useStore();
  const [filter, setFilter] = useState('');
  const [entity, setEntity] = useState('');
  const index = bundle!.index;
  const entities = useMemo(() => [...new Set(index.cases.map((c) => c.entity))].sort(), [index]);
  const cases = index.cases.filter((c) => (!entity || c.entity === entity) && (!filter || c.case_id.toLowerCase().includes(filter.toLowerCase())));
  const reviewMode = !index.study;

  return (
    <div>
      <h1>Cases</h1>
      <p className="lede">
        {index.cases.length} case{index.cases.length === 1 ? '' : 's'}, {index.summary.counts.traces} trace{index.summary.counts.traces === 1 ? '' : 's'}.
        {index.study ? <> Study <strong>{index.study.study_id}</strong> is attached with {index.study.rating_set.length} traces in the rating set.</> : <> No study is attached, so case review is available.</>}
      </p>
      <div className="filters" style={{ margin: '8px 0 16px' }}>
        <label className="field"><span>Case id</span><input type="search" value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="Filter by id" /></label>
        <label className="field"><span>Category</span>
          <select value={entity} onChange={(e) => setEntity(e.target.value)}>
            <option value="">All categories</option>
            {entities.map((e) => <option key={e} value={e}>{entityDisplay(index.lexicon, e)}</option>)}
          </select>
        </label>
        <span className="spacer" />
        <span className="muted small">{cases.length} of {index.cases.length}</span>
      </div>
      <div className="case-list">
        {cases.map((c) => (
          <article key={c.case_id} className="panel tight case-card">
            <h2><a href={hrefCase(c.case_id)}>{c.case_id}</a></h2>
            <div className="entity-line"><span className="entity-dot" style={{ background: entityColor(index.lexicon, c.entity) }} aria-hidden="true" /><span>{entityDisplay(index.lexicon, c.entity)}{c.subtype ? ` (${c.subtype})` : ''}</span></div>
            <div className="row small" style={{ marginTop: 8 }}>
              <Chip tone="neutral">{c.n_traces} traces</Chip>
              <Chip tone="neutral">{c.variants.length} variants</Chip>
              {c.flags.discordant && <Chip tone="warn" icon="!">discordant{c.flags.atypical_features.length ? `: ${c.flags.atypical_features.join(', ')}` : ''}</Chip>}
              {c.flags.incomplete && <Chip tone="warn" icon="!">incomplete: {c.flags.missing_modalities.join(', ')}</Chip>}
            </div>
            <div className="row small muted" style={{ marginTop: 8, gap: 8 }}>
              {c.variants.map((v) => <span key={v} className="mono">{v}</span>)}
            </div>
            {reviewMode && <div style={{ marginTop: 10 }}><a className="btn small" href={hrefReview(c.case_id)}>Review case</a></div>}
          </article>
        ))}
      </div>
    </div>
  );
}
