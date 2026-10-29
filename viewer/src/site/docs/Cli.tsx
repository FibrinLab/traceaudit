import { Code } from '../Code';

export default function Cli() {
  return (
    <>
      <p>
        Every command is <code>traceaudit &lt;command&gt;</code>; <code>--help</code> on any of them lists the flags. A global <code>--lexicon</code>
        overrides the packaged lexicon. Commands that take a run directory are idempotent and append to the manifest's scoring record.
      </p>

      <h2 id="text">Text-mode study</h2>
      <Code lang="shell">{`traceaudit casegen -o data/cases.jsonl --per-entity 20 --seed 20261020   # synthetic drafts for expert review
traceaudit review-sheet data/cases.jsonl -o review.csv [--import-csv review.csv]
traceaudit perturb data/cases.jsonl -o data/perturbations.jsonl --seed 20261020
traceaudit validate data/cases.jsonl --perturbations data/perturbations.jsonl   # invariant P1 on every variant
traceaudit run --client ollama|openai|anthropic|sim --model M --cases ... [--perturbations ...] \\
  --efforts low,medium,high --runs 5 --out RUN [--workers 1] [--allow-dirty REASON]
traceaudit score RUN --rule D1|D2|D3 --verify lexical|retrieval|none [--judge --judge-model M]
traceaudit export RUN -o RUN/export [--study-id ID --rating-n 100]   # the viewer bundle and blinded rating sets
traceaudit import-ratings ratings-*.jsonl ratings/
traceaudit agreement ratings/ID [--judge RUN/judge.jsonl]`}</Code>

      <h2 id="ledger-cmds">Ledger commands</h2>
      <Code lang="shell">{`traceaudit ledger audit ART.md|DIR... [--json] [--summary] [--review-sheet CSV]
traceaudit ledger cases ART.md|DIR... -o ledger_cases.jsonl
traceaudit ledger perturb ledger_cases.jsonl -o ledger_perturbations.jsonl \\
  [--expectations structured,reference,lexicon[,rationale]] [--rationale-from RUN|DIR] \\
  [--max-decisive 2] [--max-flips 3] [--anchor-op untest|flip] [--include-right] [--approve-all]
traceaudit ledger validate ledger_cases.jsonl --perturbations ledger_perturbations.jsonl
traceaudit ledger export ledger_cases.jsonl --perturbations ... -o DIR [--format json,md] [--no-evidence]
traceaudit ledger run --client sim|ollama|openai|anthropic --model M --cases ... [--perturbations ...] --out RUN [--with-ablation]
traceaudit ledger ablate RUN [--client ... | --export DIR] [--runs 1] [--mode remove|mask]
traceaudit ledger import ART... --run-dir RUN --cases ... [--perturbations ...] [--index DIR/index.jsonl]
traceaudit ledger score RUN [--rule D1|D2|D3|D1R] [--surfaces thinking,report]
traceaudit ledger validate-probes [--grid quick|default]
traceaudit ledger sample ART|DIR --n 300 --raters R01,R02 -o labels/
traceaudit ledger agreement labels/ [--results audit.json]`}</Code>

      <h2 id="checks">Checks and reports</h2>
      <Code lang="shell">{`traceaudit demo --out runs/demo [--runs 2] [--B 2000] [--judge]
traceaudit report RUN                        # Markdown from summary.json
traceaudit manifest check|show|verify RUN [--cases F --perturbations F]
traceaudit validate-probes --grid quick|default
traceaudit recall labelled_claims.jsonl      # extractor recall against hand labels`}</Code>

      <h2 id="service">Service</h2>
      <Code lang="shell">{`traceaudit serve --root serve-data --static viewer/dist --port 8080 \\
  [--anonymous analyse|none|all] [--rate 60/min] [--tokens t1:wsA,t2:wsB] \\
  [--allow-clients sim,ollama,openai,anthropic] [--operator-key anthropic=ANTHROPIC_API_KEY] \\
  [--max-calls-per-job 200] [--max-calls-per-day 2000] [--workers 1]`}</Code>
      <p>Every flag has an environment variable twin, <code>TRACEAUDIT_*</code>, which is how the container deployment sets them.</p>
    </>
  );
}
