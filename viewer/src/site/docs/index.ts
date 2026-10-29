import type { ComponentType } from 'react';
import Overview from './Overview';
import Quickstart from './Quickstart';
import Api from './Api';
import Ledger from './Ledger';
import Probes from './Probes';
import Validation from './Validation';
import Provenance from './Provenance';
import Cli from './Cli';
import Domains from './Domains';
import Service from './Service';
import Limits from './Limits';

export interface Chapter { slug: string; n: number; title: string; blurb: string; sections: Array<{ id: string; title: string }>; Component: ComponentType }

export const CHAPTERS: Chapter[] = [
  { slug: 'overview', n: 1, title: 'What traceaudit measures', blurb: 'The question, the three measurements that answer it, and what the tool deliberately is not.',
    sections: [{ id: 'question', title: 'The question' }, { id: 'measurements', title: 'Three measurements' }, { id: 'not', title: 'What it is not' }, { id: 'parts', title: 'The parts' }], Component: Overview },
  { slug: 'quickstart', n: 2, title: 'Quick start', blurb: 'Install, run the simulated demo, audit an artefact and start the service, in ten minutes and without a model.',
    sections: [{ id: 'install', title: 'Install' }, { id: 'demo', title: 'The demo' }, { id: 'audit', title: 'Audit an artefact' }, { id: 'serve', title: 'Start the service' }, { id: 'model', title: 'Point at a model' }], Component: Quickstart },
  { slug: 'api', n: 3, title: 'API reference', blurb: 'Every endpoint of the service, with a live sheet to send each request from this page.',
    sections: [{ id: 'conventions', title: 'Conventions' }, { id: 'health', title: 'GET /api/health' }, { id: 'lexicons', title: 'Lexicons' }, { id: 'analyse', title: 'POST /api/analyse' }, { id: 'ledger', title: 'POST /api/ledger' }, { id: 'case-sets', title: 'Case sets and uploads' }, { id: 'jobs', title: 'Jobs' }, { id: 'errors', title: 'Errors' }], Component: Api },
  { slug: 'ledger', n: 4, title: 'The fact ledger', blurb: 'Facts with ids, citations graded against them, twenty-four checks, and how free text becomes a ledger.',
    sections: [{ id: 'facts', title: 'Facts' }, { id: 'grades', title: 'Grades' }, { id: 'checks', title: 'The 24 checks' }, { id: 'metrics', title: 'Metrics' }, { id: 'text', title: 'Text as a ledger' }, { id: 'artefacts', title: 'Artefacts and importers' }], Component: Ledger },
  { slug: 'probes', n: 5, title: 'Probes', blurb: 'The interventions, the disclosure rules, the outcomes, and the base reference they are scored against.',
    sections: [{ id: 'variants', title: 'Variants' }, { id: 'disclosure', title: 'Disclosure rules' }, { id: 'outcomes', title: 'Outcomes' }, { id: 'hedging', title: 'Hedging' }, { id: 'ablation', title: 'Ablation' }, { id: 'paths', title: 'Two execution paths' }], Component: Probes },
  { slug: 'validation', n: 6, title: 'Validation and statistics', blurb: 'How the harness proves it recovers what was planted, how the grader will be checked against humans, and the statistics reported.',
    sections: [{ id: 'simulator', title: 'The simulated model' }, { id: 'grid', title: 'The validation grid' }, { id: 'grader', title: 'Grader validation' }, { id: 'stats', title: 'Statistics' }], Component: Validation },
  { slug: 'provenance', n: 7, title: 'Provenance', blurb: 'What is hashed, where it is recorded, and how a reviewer checks it.',
    sections: [{ id: 'what', title: 'What a hash proves' }, { id: 'trace', title: 'Per trace' }, { id: 'run', title: 'Per run' }, { id: 'verify', title: 'Verify' }], Component: Provenance },
  { slug: 'cli', n: 8, title: 'Command line', blurb: 'The commands, grouped by what they do, with the flags that matter.',
    sections: [{ id: 'text', title: 'Text-mode study' }, { id: 'ledger-cmds', title: 'Ledger commands' }, { id: 'checks', title: 'Checks and reports' }, { id: 'service', title: 'Service' }], Component: Cli },
  { slug: 'domains', n: 9, title: 'Bring your own domain', blurb: 'Nothing in the engine knows about haematology. One file, the lexicon, carries a domain.',
    sections: [{ id: 'lexicon', title: 'The lexicon' }, { id: 'cases', title: 'Cases' }, { id: 'rules', title: 'Loader rules' }, { id: 'transfer', title: 'What transfers' }], Component: Domains },
  { slug: 'service', n: 10, title: 'Self-hosting and security', blurb: 'Running the service inside an institution, how keys are handled, and how this public instance is deployed.',
    sections: [{ id: 'run', title: 'Run it' }, { id: 'keys', title: 'Keys and tokens' }, { id: 'limits', title: 'Limits' }, { id: 'public', title: 'This public instance' }], Component: Service },
  { slug: 'limits', n: 11, title: 'Research status and limits', blurb: 'What is validated, what is not yet, the known limits carried into the paper, and how to cite.',
    sections: [{ id: 'status', title: 'Status' }, { id: 'known', title: 'Known limits' }, { id: 'cite', title: 'Cite' }], Component: Limits },
];

export function chapterBySlug(slug: string): Chapter | null { return CHAPTERS.find((c) => c.slug === slug) ?? null; }
