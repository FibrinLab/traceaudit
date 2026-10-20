# Bring your own domain

traceaudit is trace analytics for any task where a model reasons over a known set
of source documents and gives a categorical answer. Nothing in the engine knows
about haematology; the clinical content lives in one file, the **lexicon**, and
the packaged haematology lexicon is just the reference domain the authors built
the study on.

A lexicon says five things:

| Key | What it holds | Needed for |
|---|---|---|
| `sections` | the document sections a case is made of (`[{id, title}]`) | rendering and the Analyse form |
| `findings` | the binary facts a document can assert, each with the words that name it (`aliases`), optional whole-phrase forms (`pos_phrases`, `neg_phrases`), optional `numeric_rule`, and canonical sentences (`pos_text`, `neg_text`) | grounding, perturbation |
| `entities` | the answer categories and their names | answer parsing, authority cues |
| `discriminators` | for each finding, whether each entity expects it `pos`, `neg` or `var` | knowledge checks, the Lexicon Atlas, simulated models |
| `linked`, `confusion`, `phrases` | associated findings, plausible wrong answers, and the phrase lists for hedging, acknowledgement, knowledge and inference detection | probes and claim typing |

A complete non-clinical example is in [`examples/lexicon-incident-triage.json`](../examples/lexicon-incident-triage.json)
(software incident triage: alerts, logs and deploy history as documents; faulty
deployment, capacity, database and disk as answers). Try it:

```bash
traceaudit serve --static viewer/dist
# then in the Analyse tab choose "Upload lexicon", pick the example, paste the documents from
# examples/incident-trace.json, and analyse; or by API:
curl -s -X POST localhost:8080/api/lexicons -H 'content-type: application/json' \
  -d "{\"lexicon\": $(python3 -c 'import json;print(json.dumps(open("examples/lexicon-incident-triage.json").read()))')}"
```

## What transfers unchanged

- Extraction, segmentation, grounding, answer parsing, the probes, the statistics,
  the service and the viewer.
- Authority cues: the cue template is a lexicon field (`cue_templates`).

## What you write per domain

- The lexicon itself. Start from the example; keep `phrases` unless your domain's
  language for hedging or inference differs.
- Cases: real or synthetic documents with a known answer. `traceaudit cases build
  docs.jsonl -o cases.jsonl --lexicon my-lexicon.json` turns `{case_id, entity,
  documents{section: text}}` records into cases, reading the truth from the documents
  with the extractor and reporting anything it could not read. The packaged generator
  (`traceaudit/domains/haematology/casegen.py`) shows how to synthesise cases from
  priors when you have none.
- Nothing else is required for the probes: decisive and anchor-loss edits are
  derived from your discriminator table (flip the finding after which another
  category fits the documents best), neutral edits and authority cues are generic.
  If you want hand-authored edits with clinical or expert rationale instead, add a
  `perturbations` block to the lexicon (`{"decisive": [{base, target, primary:
  [finding, from, to], co_edits, preconditions, rationale}], "anchor_loss": [...]}`);
  authored rows take precedence over the derived ones.

## Lexicon rules the loader enforces

- Finding ids are unique; no alias is shared by two findings.
- Every finding named in `discriminators`, `linked` or `confusion` exists.
- Every entity has at least one alias; aliases of five characters or fewer in
  capitals are matched case-sensitively (so `FL` does not match the unit `fL`).
