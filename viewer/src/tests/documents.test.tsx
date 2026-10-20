import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { render } from '@testing-library/react';
import { buildAnalyseRequest, hasAnyDocument, sectionIndex, sectionTitle, sectionsFor, titleFromId } from '../lib/documents';
import { buildSingleTraceBundle } from '../lib/analyseBundle';
import { ReportPane } from '../components/ReportPane';
import { lexiconLabel, type AnalyseResponse } from '../lib/api';
import type { Section } from '../types';

const incident = JSON.parse(readFileSync(resolve(__dirname, '../../public/examples/incident-trace.json'), 'utf8')) as { documents: Record<string, string>; reasoning: string; answer: string };
const incidentLexicon = JSON.parse(readFileSync(resolve(__dirname, '../../public/examples/lexicon-incident-triage.json'), 'utf8')) as { domain: string; version: string; sections: Section[]; entities: Array<{ id: string; display: string }>; findings: Array<{ id: string; display: string; kind: string }> };

describe('sections', () => {
  it('uses the declared sections in order and humanises undeclared keys', () => {
    const secs = sectionsFor({ logs: 'x', alerts: 'y', deploys: '', extra_notes: 'z' }, incidentLexicon.sections);
    expect(secs.map((s) => s.id)).toEqual(['alerts', 'logs', 'deploys', 'extra_notes']);
    expect(secs.map((s) => s.title)).toEqual(['Alerts', 'Logs', 'Deploy history', 'Extra notes']);
    expect(sectionTitle(incidentLexicon.sections, 'deploys')).toBe('Deploy history');
    expect(sectionTitle(incidentLexicon.sections, 'deploy_log')).toBe('Deploy log');
    expect(sectionIndex(incidentLexicon.sections, 'logs')).toBe(1);
    expect(sectionIndex(incidentLexicon.sections, 'nope')).toBe(Number.MAX_SAFE_INTEGER);
    expect(titleFromId('deploy-history')).toBe('Deploy history');
  });

  it('falls back to the document keys, in their own order and humanised, when nothing declares sections', () => {
    const secs = sectionsFor({ ticket: 't', chat_log: 'c', 'runbook-notes': 'r' }, undefined);
    expect(secs.map((s) => s.id)).toEqual(['ticket', 'chat_log', 'runbook-notes']);
    expect(secs.map((s) => s.title)).toEqual(['Ticket', 'Chat log', 'Runbook notes']);
    expect(sectionsFor({}, null)).toEqual([]);
    expect(sectionsFor(null, [{ id: 'a', title: '' }])).toEqual([{ id: 'a', title: 'A' }]);
  });
});

describe('buildAnalyseRequest', () => {
  it('sends documents in section order with titles, keeping empty documents, and the chosen lexicon_id', () => {
    const req = buildAnalyseRequest({ documents: { logs: incident.documents.logs, alerts: incident.documents.alerts }, sections: incidentLexicon.sections, reasoning: incident.reasoning, answer: incident.answer, lexiconId: 'example:incident-triage', entity: 'BAD_DEPLOY' });
    expect(Object.keys(req.documents!)).toEqual(['alerts', 'logs', 'deploys']);
    expect(req.documents!.deploys).toBe('');
    expect(req.titles).toEqual({ alerts: 'Alerts', logs: 'Logs', deploys: 'Deploy history' });
    expect(req.lexicon_id).toBe('example:incident-triage');
    expect(req.entity).toBe('BAD_DEPLOY');
    expect(req.truth).toBeUndefined();
    const uploaded = buildAnalyseRequest({ documents: { notes: 'n' }, sections: [{ id: 'notes', title: 'Notes' }], reasoning: 'r', answer: 'a', lexiconId: 'lex-abc' });
    expect(uploaded.lexicon_id).toBe('lex-abc');
    expect(uploaded.entity).toBeUndefined();
    const none = buildAnalyseRequest({ documents: { other: 'o' }, sections: [], reasoning: 'r', answer: 'a' });
    expect(none.lexicon_id).toBeUndefined();
    expect(none.documents).toEqual({ other: 'o' });
    expect(none.titles).toEqual({ other: 'Other' });
    expect(hasAnyDocument({ a: '  ', b: '' })).toBe(false);
    expect(hasAnyDocument({ a: 'x' })).toBe(true);
  });

  it('labels lexicons by domain and source', () => {
    expect(lexiconLabel({ id: 'example:incident-triage', name: 'incident-triage', domain: 'incident-triage', version: '1', sections: [], n_findings: 0, n_entities: 0, source: 'example' })).toBe('Incident triage (example)');
    expect(lexiconLabel({ id: 'lex-1', name: null, domain: 'incident-triage', version: '1', sections: [], n_findings: 0, n_entities: 0, source: 'upload' })).toBe('Incident triage (uploaded)');
    expect(lexiconLabel({ id: 'lex-2', name: 'Ops', domain: 'incident-triage', version: '1', sections: [], n_findings: 0, n_entities: 0, source: 'upload' })).toBe('Ops (uploaded)');
  });
});

describe('sections-driven rendering', () => {
  it('ReportPane shows one heading per declared section, in order, with the declared titles', () => {
    const { container } = render(<ReportPane reports={incident.documents} sections={incidentLexicon.sections} />);
    expect([...container.querySelectorAll('h3')].map((h) => h.textContent)).toEqual(['Alerts', 'Logs', 'Deploy history']);
    expect(container.textContent).toContain('Release 2026.10.20-3');
  });

  it('ReportPane falls back to humanised document keys for a bundle case without sections', () => {
    const { container } = render(<ReportPane reports={{ ticket: 'T-1 opened', chat_log: 'ops: looking' }} />);
    expect([...container.querySelectorAll('h3')].map((h) => h.textContent)).toEqual(['Ticket', 'Chat log']);
  });

  it('the analysed bundle carries the response sections and lexicon display names', () => {
    const res: AnalyseResponse = {
      case: { case_id: 'ANL-001', entity: 'BAD_DEPLOY', reports: incident.documents, truth: {}, finding_spans: {}, sections: incidentLexicon.sections },
      lexicon: { id: 'lex-1', domain: incidentLexicon.domain, version: incidentLexicon.version, entities: incidentLexicon.entities.map((e) => ({ id: e.id, display: e.display })), findings: incidentLexicon.findings.map((f) => ({ id: f.id, display: f.display, kind: f.kind })) },
      domain: incidentLexicon.domain,
      claims: [], grounding: null, map: null, parsed_answer: { entity: 'BAD_DEPLOY' }, oracle: 'extracted',
    };
    const req = buildAnalyseRequest({ documents: incident.documents, sections: incidentLexicon.sections, reasoning: incident.reasoning, answer: incident.answer, lexiconId: 'lex-1' });
    const built = buildSingleTraceBundle(req, res, { version: 'unknown', entities: [], findings: [] });
    expect(built.caseFile.case.sections).toEqual(incidentLexicon.sections);
    expect(Object.keys(built.caseFile.case.reports)).toEqual(['alerts', 'logs', 'deploys']);
    expect(built.bundle.index.lexicon.entities.find((e) => e.id === 'BAD_DEPLOY')?.display).toBe('Faulty deployment');
    expect(built.bundle.index.run.manifest.notes).toContain('domain: incident-triage');
    const { container } = render(<ReportPane reports={built.caseFile.case.reports} sections={built.caseFile.case.sections} />);
    expect([...container.querySelectorAll('h3')].map((h) => h.textContent)).toEqual(['Alerts', 'Logs', 'Deploy history']);
  });
});
