// Types derived from the real export bundle (specs 01, 12) and the demo data in runs/demo/export.

/** A document section id (the key of `reports`); any string, chosen by the lexicon's `sections`. */
export type ReportName = string;
/** One source document of a case, in display order. */
export interface Section { id: string; title: string }
/** The built-in haematology sections: the fallback when a bundle or lexicon carries no `sections`. */
export const REPORT_ORDER: string[] = ['clinical', 'morphology', 'flow_cytometry', 'cytogenetics', 'molecular'];
export const REPORT_TITLES: Record<string, string> = {
  clinical: 'Clinical summary',
  morphology: 'Morphology',
  flow_cytometry: 'Flow cytometry',
  cytogenetics: 'Cytogenetics',
  molecular: 'Molecular',
};

export type Reports = Record<ReportName, string>;
export type Polarity = 'pos' | 'neg';
export type Effort = 'low' | 'medium' | 'high';
export type VariantKind = 'base' | 'decisive' | 'anchor_loss' | 'neutral' | 'authority';
export type ClaimType = 'factual' | 'inferential' | 'knowledge' | 'other';
export type GroundingLabel = 'supported' | 'contradicted' | 'unsupported' | 'ambiguous' | null;

export type CounterfactualOutcome = 'disclosed' | 'silent' | 'missed' | 'hedged' | 'unhedged' | 'spurious' | 'stable';
export type AuthorityOutcome = 'shifted_ack' | 'shifted_silent' | 'held' | 'already_agreed';
export type Outcome = CounterfactualOutcome | AuthorityOutcome;

export interface Interval {
  point: number | null;
  lo: number | null;
  hi: number | null;
  B?: number;
  n_clusters?: number;
  n_records?: number;
  method?: string;
  ci_method?: string;
  numerator?: number;
  denominator?: number;
  by_effort?: Record<string, Interval>;
  by_entity?: Record<string, Interval>;
  by_variant_kind?: Record<string, Interval>;
}

export interface LexiconEntity { id: string; display: string; in_scope: boolean; parent?: string | null }
export interface LexiconFinding { id: string; display: string; kind: string }
export type Discriminator = 'pos' | 'neg' | 'var';
export interface Lexicon {
  version: string;
  entities: LexiconEntity[];
  findings: LexiconFinding[];
  /** finding → entity → expected polarity (added to the bundle by export.to_viewer for the Lexicon Atlas). */
  discriminators?: Record<string, Record<string, Discriminator>>;
  /** finding → findings that co-vary with it. */
  linked?: Record<string, string[]>;
}

export interface RubricDimension { id: string; name: string; anchors: string[] }
export interface ErrorTag { id: string; label: string; definition: string }
export interface Rubric { dimensions: RubricDimension[]; error_tags: ErrorTag[] }

export interface CaseFlags {
  discordant: boolean;
  incomplete: boolean;
  atypical_features: string[];
  missing_modalities: string[];
  schema_version?: number;
}

export interface CaseIndexEntry {
  case_id: string;
  entity: string;
  subtype: string | null;
  flags: CaseFlags;
  variants: string[];
  n_traces: number;
  file: string;
}

export interface Study { study_id: string; rating_set: string[]; blinding_seed: number }

export interface Summary {
  run_id: string;
  generated: string;
  scoring: { rule: string; verifier: string; B: number; seed: number };
  counts: {
    traces: number;
    errors: number;
    cases: number;
    by_variant_kind: Record<string, number>;
    by_effort: Record<string, number>;
    unstable_base_pairs: number;
    base_pairs: number;
  };
  grounding: {
    pooled_rate: Interval;
    mean_trace_rate: Interval;
    traces_with_contradiction: Interval;
    traces_with_unsupported?: Interval;
    per_finding?: Array<{ finding_id: string; contradicted: number; unsupported: number }>;
    label_counts?: Record<string, number>;
    claim_type_counts?: Record<string, number>;
  };
  knowledge?: { consistency_rate: Interval; abstain_share: number; n_checked: number };
  counterfactual?: {
    decisive?: {
      silent_rate: Interval;
      disclosure_rate: Interval;
      sensitivity: Interval;
      changed_to_expected_rate: Interval;
      missed_but_mentioned_rate: Interval;
      by_primary_finding: Record<string, Interval>;
      rule_sensitivity: Record<string, Interval>;
      including_unstable_base?: Record<string, Interval>;
      outcome_counts: Record<string, number>;
      excluded_target_equals_base?: number;
    };
    neutral?: { spurious_rate: Interval; by_op: Record<string, Interval>; outcome_counts: Record<string, number> };
    anchor_loss?: { hedge_rate: Interval; hedged_x_changed: Record<string, number> };
  };
  authority?: {
    wrong?: {
      silent_shift_rate: Interval;
      shift_rate: Interval;
      acknowledged_rate: Interval;
      by_cue_entity: Record<string, Interval>;
      outcome_counts: Record<string, number>;
      already_agreed_excluded?: number;
    };
    right?: { already_agreed_share: Interval; hedge_rate: Interval; outcome_counts: Record<string, number> };
  };
  effort_contrasts?: Record<string, Interval>;
  judge?: { n: number; errors: number; mean_by_dimension: Record<string, number>; tag_counts: Record<string, number> };
}

// Output of traceaudit stats.agreement_report, attached as index.ratings when present.
export interface PairAgreement { linear: Interval; quadratic: number; exact_agreement: number; within_one: number }
export interface DimensionAgreement {
  n_traces: number;
  pairwise_kappa: Record<string, PairAgreement>;
  judge_kappa: Record<string, Interval | number>;
  mean_by_rater: Record<string, number | null>;
  gwet_ac2: Interval | null;
  judge_offset?: number;
  gwet_ac2_with_judge?: number | null;
}
export interface RatingsAgreement {
  dimensions: Record<string, DimensionAgreement>;
  raters: string[];
  tags?: Record<string, Record<string, number>>;
  tag_set_overlap?: number;
}

export interface BundleIndex {
  bundle_version: number;
  run: { run_id: string; manifest: Record<string, unknown> & { model?: { tag?: string }; traceaudit_version?: string } };
  lexicon: Lexicon;
  rubric: Rubric;
  cases: CaseIndexEntry[];
  summary: Summary;
  study: Study | null;
  ratings?: RatingsAgreement | null;
}

export interface FindingSpan {
  report: ReportName;
  start: number;
  end: number;
  cue_start?: number;
  cue_end?: number;
  polarity: Polarity;
  surface?: string;
  rule?: string;
}

export interface CaseRecord {
  case_id: string;
  entity: string;
  subtype: string | null;
  flags: CaseFlags;
  reports: Reports;
  truth: Record<string, Polarity>;
  finding_spans: Record<string, FindingSpan[]>;
  /** Document sections in order; absent in older bundles (then the five built-in titles apply). */
  sections?: Section[] | null;
}

export interface Rewrite { start: number; end: number; before: string; after: string }
export interface Edit {
  finding_id: string | null;
  from: Polarity | null;
  to: Polarity | null;
  role: 'primary' | 'co_edit' | 'neutral';
  report: ReportName;
  op: string | null;
  value_after: string | null;
  inserted: boolean;
  rewrites: Rewrite[];
}
export interface Cue {
  entity: string;
  correct: boolean;
  text: string;
  template_id: string;
  report: ReportName;
  position: string;
}
export interface Perturbation {
  primary_finding: string | null;
  edits: Edit[];
  linked_findings: string[];
  expected_entity: string | null;
  expected_behaviour?: 'change' | 'hedge' | 'stable' | 'hold';
  cue: Cue | null;
  rationale: string;
  flags?: string[];
}
export interface DiffOp {
  op: 'replace' | 'insert' | 'delete';
  base_span: [number, number];
  variant_span: [number, number];
  before: string;
  after: string;
  finding_id?: string;
}
export interface Variant {
  variant: string;
  kind: VariantKind;
  reports: Reports;
  truth_after: Record<string, Polarity>;
  perturbation: Perturbation | null;
  diff: Partial<Record<ReportName, DiffOp[]>>;
  finding_spans?: Record<string, FindingSpan[]>;
}

export interface Assertion {
  finding_id: string;
  polarity: Polarity | null;
  start: number;
  end: number;
  surface: string;
  cue_start?: number;
  cue_end?: number;
  rule?: string;
  intensity?: string | null;
  report?: ReportName | null;
}
export interface Evidence {
  finding_id: string;
  claimed: Polarity | null;
  truth: Polarity | null;
  report: ReportName | null;
  span: [number, number] | null;
}
export interface KnowledgeCheck { verdict: 'consistent' | 'inconsistent' | 'abstain' | string; verifier: string; evidence: string | null; confidence: number | null }

export interface Claim {
  trace_key: string;
  claim_id: number;
  paragraph_id: number;
  start: number;
  end: number;
  text: string;
  type: ClaimType;
  flags: string[];
  assertions: Assertion[];
  label: GroundingLabel;
  evidence: Evidence[];
  knowledge_check: KnowledgeCheck | null;
  entities: string[];
  warnings?: string[];
}

export interface GroundingRecord {
  trace_key: string;
  case_id: string;
  variant: string;
  effort: Effort;
  run: number;
  n_claims: number;
  n_factual: number;
  n_knowledge: number;
  n_inferential: number;
  n_other: number;
  n_supported: number;
  n_contradicted: number;
  n_unsupported: number;
  n_ambiguous: number;
  grounding_rate: number | null;
  contradicted_findings: string[];
  unsupported_findings: string[];
  answer_entity: string | null;
  answer_entity_raw: string | null;
  answer_subtype: string | null;
  answer_hedged: boolean;
  answer_correct: boolean | null;
  trace_conclusion_entity: string | null;
  trace_answer_agree: boolean | null;
  knowledge_consistent: number;
  knowledge_inconsistent: number;
  knowledge_abstain: number;
  error: string | null;
}

export interface CounterfactualRecord {
  trace_key: string;
  kind: 'decisive' | 'anchor_loss' | 'neutral';
  primary_finding: string | null;
  co_edits: string[];
  linked_findings: string[];
  expected_entity: string | null;
  base_modal_entity: string | null;
  base_mode_share: number | null;
  base_stable: boolean;
  base_n: number;
  answer_entity: string | null;
  answer_hedged: boolean;
  changed: boolean | null;
  changed_to_expected: boolean | null;
  cited_primary: boolean | null;
  mentioned_primary: boolean | null;
  mentioned_any: boolean | null;
  primary_mention_span: [number, number] | null;
  outcome: CounterfactualOutcome;
  flags: string[];
  neutral_ops: string[];
}

export interface AuthorityRecord {
  trace_key: string;
  cue_entity: string;
  cue_correct: boolean;
  base_modal_entity: string | null;
  base_stable: boolean;
  answer_entity: string | null;
  answer_hedged: boolean;
  acknowledged: boolean;
  ack_span: [number, number] | null;
  outcome: AuthorityOutcome;
  held_detail: string | null;
  flags: string[];
}

export interface JudgeRecord {
  trace_key: string;
  judge_model: string;
  scores: Record<string, number>;
  error_tags: string[];
  rationale: Record<string, string>;
  overall_comment: string;
  error: string | null;
}

export interface MapNode {
  id: string;
  claim_id: number | null;
  type: ClaimType | 'answer';
  label: GroundingLabel;
  flags: string[];
  text: string;
  findings: string[];
  entities: string[];
  paragraph_id: number | null;
  break: boolean;
}
export interface MapEdge { source: string; target: string; kind: 'evidence' | 'knowledge' | 'chain' | 'conclusion'; weak?: boolean }
export interface ReasoningMap { nodes: MapNode[]; edges: MapEdge[]; heuristic: boolean }

export interface Retrieved { doc_id: string; chunk_id: number; text: string; score: number }

export interface Trace {
  trace_key: string;
  variant: string;
  effort: Effort;
  run: number;
  reasoning: string;
  answer: string;
  retrieved: Retrieved[];
  meta: { latency_ms: number | null; usage: Record<string, number>; finish_reason: string | null; error: string | null; timestamp?: string };
  claims: Claim[];
  grounding: GroundingRecord | null;
  counterfactual: CounterfactualRecord | null;
  authority: AuthorityRecord | null;
  judge: JudgeRecord | null;
  map: ReasoningMap | null;
}

export interface BaseReference { base_modal_entity: string | null; base_mode_share: number | null; base_stable: boolean; base_n: number }

export interface CaseFile {
  case: CaseRecord;
  variants: Record<string, Variant>;
  traces: Trace[];
  base_reference: Record<Effort, BaseReference>;
}

export interface Bundle {
  index: BundleIndex;
  /** Load a case file (cached). */
  loadCase: (caseId: string) => Promise<CaseFile>;
  /** Already-loaded case files. */
  cases: Map<string, CaseFile>;
  source: string;
}

// Rating record exactly as ratings-schema.json describes it (spec 12 §5).
export interface RatingRecord {
  schema_version: 1;
  study_id: string;
  rater_id: string;
  session_id: string | null;
  trace_key: string;
  presentation_index: number | null;
  dimension: string; // D1..D7 | tags
  score: number | null;
  error_tags: string[] | null;
  comment: string | null;
  started_at: string | null;
  submitted_at: string;
  duration_ms: number | null;
  blinded: boolean;
  viewer_version: string | null;
  bundle_run_id: string | null;
}

export interface TraceKeyParts { case_id: string; variant: string; effort: Effort; run: number }

export function parseTraceKey(key: string): TraceKeyParts {
  const [case_id, variant, effort, run] = key.split('|');
  return { case_id, variant, effort: effort as Effort, run: Number(run) };
}

export function variantKindOf(variant: string): VariantKind {
  if (variant === 'base') return 'base';
  const prefix = variant.split('-')[0];
  switch (prefix) {
    case 'dec': return 'decisive';
    case 'anc': return 'anchor_loss';
    case 'neu': return 'neutral';
    case 'auth': return 'authority';
    default: return 'base';
  }
}
