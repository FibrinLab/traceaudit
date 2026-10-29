import { describe, expect, it } from 'vitest';
import {
  GRADE_TONE, candidateCounts, coverageCategory, coverageCounts, describeUncited, disagreeingIds, filterFacts, gradeColor, gradeTone, groupFacts, parseLedgerResult, tokeniseThinking, uncitedAssertion,
  type Fact, type LedgerResult,
} from '../lib/ledger';
import { buildLedgerRequest } from '../views/AnalyseLedgerView';

import raw from '../../mock/fixtures/ledger-result.json';

const fact = (over: Partial<Fact>): Fact => ({
  id: 'p_1', source: 'patient', section: 'immunophenotyping', field: 'CD5', value: 'Positive', evidence: '', candidate: null, polarity: 'pos',
  informative: true, referenced_in_thinking: false, cited_in_report: false, cited_in_rationale: false, ignored: false, ...over,
});

describe('grade → colour mapping', () => {
  it('maps every grade to the stylesheet tone the spec names', () => {
    expect(GRADE_TONE.agree).toBe('good');
    expect(GRADE_TONE.disagree).toBe('bad');
    expect(GRADE_TONE.unverifiable).toBe('warn');
    expect(GRADE_TONE.reference).toBe('neutral');
    expect(GRADE_TONE.not_found).toBe('bad outline');
    expect(GRADE_TONE.not_mentioned).toBe('warn outline');
  });
  it('resolves colours from tones and falls back to neutral for unknown grades', () => {
    expect(gradeColor('agree')).toBe('var(--supported)');
    expect(gradeColor('disagree')).toBe('var(--contradicted)');
    expect(gradeColor('not_found')).toBe('var(--contradicted)');
    expect(gradeColor('unverifiable')).toBe('var(--unsupported)');
    expect(gradeColor('reference')).toBe('var(--text-2)');
    expect(gradeTone('something-new')).toBe('neutral');
    expect(gradeTone(null)).toBe('neutral');
  });
});

describe('thinking tokenisation', () => {
  const ids = ['p_1', 'p_12', 'c_111', 'w_65'];
  it('splits text into ids, candidates and plain text, flagging unknown ids', () => {
    const t = tokeniseThinking('CD5+ (p_1) and p_12; see w_65 and p_999. Fits CLL/SLL, not FL.', ids, ['CLL/SLL', 'FL', 'MCL']);
    expect(t.filter((x) => x.kind === 'id').map((x) => (x as { id: string }).id)).toEqual(['p_1', 'p_12', 'w_65', 'p_999']);
    expect(t.filter((x) => x.kind === 'id').map((x) => (x as { known: boolean }).known)).toEqual([true, true, true, false]);
    expect(t.filter((x) => x.kind === 'candidate').map((x) => (x as { candidate: string }).candidate)).toEqual(['CLL/SLL', 'FL']);
    expect(t.map((x) => x.text).join('')).toBe('CD5+ (p_1) and p_12; see w_65 and p_999. Fits CLL/SLL, not FL.');
  });
  it('does not match ids inside longer words and matches candidates as whole words, case-insensitively', () => {
    const t = tokeniseThinking('icd_11_coding del_11q p_1x and FLOW vs fl.', ids, ['FL']);
    expect(t.filter((x) => x.kind === 'id')).toEqual([]);
    const cands = t.filter((x) => x.kind === 'candidate');
    expect(cands).toHaveLength(1);
    expect(cands[0].text).toBe('fl');
    expect((cands[0] as { candidate: string }).candidate).toBe('FL');
  });
  it('counts candidate mentions, listing unnamed candidates at zero', () => {
    expect(candidateCounts('CLL/SLL twice: CLL/SLL. MCL once.', ['CLL/SLL', 'MCL', 'HCL'])).toEqual({ 'CLL/SLL': 2, MCL: 1, HCL: 0 });
  });
  it('returns the whole text as one token when nothing matches', () => {
    expect(tokeniseThinking('plain words', [], [])).toEqual([{ kind: 'text', text: 'plain words' }]);
    expect(tokeniseThinking('', ids, ['FL'])).toEqual([]);
  });
});

describe('coverage strip categorisation', () => {
  it('orders cited over referenced over ignored, with grey for untested-and-ignored', () => {
    expect(coverageCategory(fact({ cited_in_report: true, referenced_in_thinking: true }))).toBe('cited');
    expect(coverageCategory(fact({ cited_in_rationale: true }))).toBe('cited');
    expect(coverageCategory(fact({ referenced_in_thinking: true }))).toBe('referenced');
    expect(coverageCategory(fact({ ignored: true, informative: true }))).toBe('ignored');
    expect(coverageCategory(fact({ ignored: true, informative: false, polarity: 'untested', value: 'Not performed' }))).toBe('untested');
  });
  it('counts only patient and context facts', () => {
    const facts = [
      fact({ id: 'p_1', cited_in_report: true }),
      fact({ id: 'c_2', source: 'context', referenced_in_thinking: true }),
      fact({ id: 'p_3', ignored: true }),
      fact({ id: 'p_4', ignored: true, informative: false }),
      fact({ id: 'w_5', source: 'who', cited_in_report: true }),
    ];
    expect(coverageCounts(facts)).toEqual({ cited: 1, referenced: 1, ignored: 1, untested: 1 });
  });
});

describe('ledger result parsing of the service fixture', () => {
  const r: LedgerResult = parseLedgerResult(raw);
  it('keeps the top-level verdict, checks and metrics', () => {
    expect(r.case_id).toBe('case_003');
    expect(r.decision).toBe('CLL/SLL');
    expect(r.truth).toBe('CLL/SLL');
    expect(r.candidates).toHaveLength(8);
    expect(r.checks).toHaveLength(24);
    expect(r.checks.filter((c) => c.status === 'FAIL')).toHaveLength(r.metrics.checks_failed);
    expect(r.metrics.checks_total).toBe(24);
    expect(r.metrics.facts).toBe(111);
    expect(r.metrics.patient_facts + r.metrics.context_facts + r.metrics.reference_facts).toBe(111);
    expect(r.metrics.candidates_named_in_thinking).toEqual({ 'CLL/SLL': 1 });
  });
  it('keeps the report sections with graded citations and the facts in ledger order', () => {
    expect(r.sections.map((s) => s.title)).toEqual(['ICD codes:', 'Summary of diagnosis:', 'Immunophenotyping:', 'Morphology:', 'Molecular:', 'Cytogenetics:']);
    const grades = new Set(r.sections.flatMap((s) => s.segments.flatMap((seg) => seg.cited.map((c) => c.grade))));
    expect([...grades].sort()).toEqual(['agree', 'not_mentioned', 'reference', 'unverifiable']);
    expect(r.facts).toHaveLength(111);
    expect(r.facts[0]).toMatchObject({ id: 'p_1', field: 'CD5', value: 'Positive', cited_in_report: true });
    expect(r.facts.filter((f) => f.ignored)).toHaveLength(r.metrics.ignored);
    expect(r.facts.filter((f) => f.ignored && f.informative)).toHaveLength(r.metrics.ignored_informative);
  });
  it('keeps thinking, rationale and ablation', () => {
    expect(r.thinking?.ids).toHaveLength(22);
    expect(r.thinking?.candidates).toEqual(['CLL/SLL']);
    expect(r.rationale?.differential).toHaveLength(8);
    expect(r.rationale?.differential[0]).toMatchObject({ diagnosis: 'CLL/SLL', verdict: 'favoured' });
    expect(r.rationale?.differential[0].criteria[0]).toMatchObject({ criterion: 'CD5 positivity', status: 'met', ids: ['w_62', 'p_1'] });
    expect(r.ablation).toEqual({ removed_ids: ['p_1', 'p_4', 'p_23', 'p_55', 'p_57'], decision_before: 'CLL/SLL', decision_after: 'CLL/SLL', changed: false });
  });
  it('groups facts by source then section in first-appearance order and filters them', () => {
    const groups = groupFacts(r.facts);
    expect(groups.map((g) => g.source)).toEqual(['patient', 'patient', 'patient', 'patient', 'context', ...Array(8).fill('who')]);
    expect(groups[0]).toMatchObject({ source: 'patient', section: 'immunophenotyping' });
    expect(groups[0].facts).toHaveLength(16);
    const dis = disagreeingIds(r.sections);
    expect(dis.size).toBe(0);
    expect(filterFacts(r.facts, 'ignored', '', dis)).toHaveLength(39);
    expect(filterFacts(r.facts, 'ignored_informative', '', dis)).toHaveLength(28);
    expect(filterFacts(r.facts, 'cited', '', dis).every((f) => f.cited_in_report || f.cited_in_rationale)).toBe(true);
    expect(filterFacts(r.facts, 'disagreements', '', dis)).toEqual([]);
    expect(filterFacts(r.facts, 'all', 'cd23', dis).map((f) => f.id)).toContain('p_4');
    expect(coverageCounts(r.facts).cited + coverageCounts(r.facts).referenced + coverageCounts(r.facts).ignored + coverageCounts(r.facts).untested).toBe(69);
  });
  it('rejects shapes the page cannot render', () => {
    expect(() => parseLedgerResult(null)).toThrow(/not an object/);
    expect(() => parseLedgerResult({ checks: 'no' })).toThrow(/checks/);
    expect(() => parseLedgerResult({ checks: [{ id: 'x', status: 'MAYBE' }] })).toThrow(/malformed check/);
    const minimal = parseLedgerResult({ decision: 'A', truth: 'B', checks: [{ id: 'a', title: 'A', status: 'FAIL', detail: '' }], facts: [] });
    expect(minimal.metrics.checks_failed).toBe(1);
    expect(minimal.sections).toEqual([]);
    expect(minimal.thinking).toBeNull();
  });
});

describe('request building', () => {
  it('sends {case, trace} JSON structured and anything else as markdown', () => {
    expect(buildLedgerRequest('# Reasoning trace\n| p_1 | CD5 |')).toEqual({ markdown: '# Reasoning trace\n| p_1 | CD5 |' });
    expect(buildLedgerRequest('{"case": {"id": 1}, "trace": {"thinking": "x"}}')).toEqual({ case: { id: 1 }, trace: { thinking: 'x' } });
    expect(buildLedgerRequest('{"not": "a trace"}')).toEqual({ markdown: '{"not": "a trace"}' });
  });
});

describe('uncited assertions', () => {
  it('parses the service object shape and still accepts the old string shape', () => {
    const o = uncitedAssertion({ field: 'CD10', stated: 'positive', fact_id: 'p_10', value: 'Negative', grade: 'disagree' });
    expect(o).toEqual({ field: 'CD10', stated: 'positive', fact_id: 'p_10', value: 'Negative', grade: 'disagree' });
    expect(describeUncited(o)).toBe('CD10: positive vs p_10 (Negative)');
    expect(uncitedAssertion('CD10 positive')).toEqual({ field: 'CD10 positive', grade: 'unknown' });
    expect(describeUncited({ field: 'BRAF', grade: 'unknown_fact' })).toBe('BRAF');
  });
  it('keeps uncited assertions on parsed segments', () => {
    const copy = JSON.parse(JSON.stringify(raw));
    copy.sections[0].segments[0].uncited_assertions = [{ field: 'CD10', stated: 'positive', fact_id: 'p_10', value: 'Negative', grade: 'disagree' }];
    const r = parseLedgerResult(copy);
    expect(r.sections[0].segments[0].uncited_assertions[0].grade).toBe('disagree');
  });
});
