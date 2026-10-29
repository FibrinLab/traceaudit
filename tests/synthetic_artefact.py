"""A synthetic engine artefact with the structure of a real per-case trace page and none of its content.

Vocabulary is invented (candidates K1..K8, panel markers mk1..mk16, shapes, GENEnn variants, generic cytogenetic
nomenclature). The numbers mirror what an engine run looks like: 111 facts (61 patient, 8 context, 42 reference ids
in 40 rows), a thinking that names one candidate, a six-section report with one dropped segment and a contract
warning, an eight-way rationale with criteria, three discriminators, and an ablation that changed nothing.
`artefact_text()` is the Markdown the engine writes; `copied_text()` is the same page copied from a browser.
"""
from __future__ import annotations

import re

from traceaudit import ledger
from traceaudit.importers import render_artefact

F = ledger.Fact
CANDIDATES = ["K1", "K2", "K3", "K4", "K5", "K6", "K7", "K8"]
CASE_ID = "SYN-003"


def build_case() -> ledger.LedgerCase:
    facts: list[F] = []
    panel = [("mk1", "Positive", "positive for mk1"), ("mk2", "Positive", "positive for mk1 mk2"), ("mk3", "Positive", "positive for mk1 mk2 mk3"),
             ("mk4", "Positive", "positive for mk1 mk2 mk3 mk4"), ("mk5", "Weak", "weak mk5"), ("mk6", "Positive", "mk6 strong mk7"), ("mk7", "Strong", "strong mk7"),
             ("mk8", "Negative", "negative for mk8"), ("mk9", "Positive", "positive for mk1 mk2 mk3 mk4 mk9"), ("mk10", "Negative", "negative for mk8 mk10"),
             ("mk11", "Not performed", ""), ("mk12", "Weak", "weak mk12 expression"), ("mk13", "Not performed", ""), ("mk14", "Not performed", ""),
             ("mk15", "Not performed", ""), ("mk16", "Not performed", "")]
    for i, (fld, val, ev) in enumerate(panel, 1):
        facts.append(F(f"p_{i}", "patient", "panel", fld, val, ev))
    morph = [("shape_a", "Not mentioned", ""), ("shape_b", "Not mentioned", ""),
             ("shape_c", "Positive", "Occasional larger forms with shape_c features account for approximately 8% of cells."),
             ("shape_d", "Not mentioned", ""), ("shape_e", "Positive", "Occasional larger forms with shape_e features account for approximately 8% of cells."),
             ("shape_f", "Negative", "inconspicuous shape_f"), ("shape_g", "Positive", "small mature forms with shape_g"),
             ("shape_h", "Positive", "Frequent shape_h forms are present."), ("shape_i", "Not mentioned", "")]
    for i, (fld, val, ev) in enumerate(morph, 17):
        facts.append(F(f"p_{i}", "patient", "morphology", fld, val, ev))
    neg_ev = "No pathogenic or likely pathogenic variants were detected in the regions analysed within the listed genes."
    for i in range(26, 54):
        g = f"GENE{i - 25:02d}_variant"
        if i == 46:
            facts.append(F("p_46", "patient", "molecular", g, "Positive", "Likely pathogenic missense variant in GENE21 at 38.8% VAF detected by sequencing."))
        elif i == 52:
            facts.append(F("p_52", "patient", "molecular", g, "Positive", "Likely pathogenic missense variant in GENE27 at 47% VAF detected by sequencing."))
        else:
            facts.append(F(f"p_{i}", "patient", "molecular", g, "Negative", neg_ev))
    facts.append(F("p_54", "patient", "molecular", "ig_mutated", "mutated", "Following the 98% identity cut-off this case belongs to the mutated category."))
    cyto = [("del_3q", "Positive", "clonal loss at 3q"), ("del_5q", "Not performed", ""), ("del_7p", "Negative", "no evidence of clonal loss at 7p"),
            ("del_9q", "Not performed", ""), ("gain_of_2", "Not performed", ""), ("t_2_5", "Not performed", ""), ("t_4_8", "Not performed", "")]
    for i, (fld, val, ev) in enumerate(cyto, 55):
        facts.append(F(f"p_{i}", "patient", "cytogenetics", fld, val, ev))
    ctx = [("level_a", "169"), ("level_b", "260"), ("level_c", "5.4"), ("level_d", "97.5"), ("level_e", "90.5"),
           ("marker_x", "Absent"), ("marker_y", "Present"), ("marker_z", "Absent")]
    for i, (fld, val) in enumerate(ctx, 104):
        facts.append(F(f"c_{i}", "context", "clinical context", fld, val, ""))
    essential = {"K1": "See #1.", "K2": "mk10 positive with shape_c negative", "K3": "GENE05 variant detected and shape_i positive",
                 "K4": "marker_x present; mk10 negative; mk4 negative", "K5": "mk1 positive; mk14 positive", "K6": "shape_f positive; GENE05 variant not detected",
                 "K7": "shape_i positive; GENE05 variant not detected", "K8": "mk1 negative; mk4 positive; shape_g positive; marker_x present"}
    desirable = {"K1": "See #1.", "K2": "mk12 positive", "K3": "mk13 positive and mk14 positive", "K4": "GENE07 variant detected",
                 "K5": "mk15 positive", "K6": "GENE05 variant not detected", "K7": "marker_z absent", "K8": "mk10 negative"}
    wid = 62
    for k, cand in enumerate(CANDIDATES, 1):
        rows = [("definition", f"{cand} is a category of the synthetic domain defined by its marker pattern."),
                ("icd_o_coding", f"9{k}00/3 {cand} category"), ("icd_11_coding", f"2A8{k}.0 {cand} category"),
                ("essential_diagnostic_criteria", essential[cand]), ("desirable_diagnostic_criteria", desirable[cand])]
        for fld, val in rows:
            n_ids = 3 if (cand == "K5" and fld == "icd_o_coding") else 1   # one reference row carrying three ids
            for _ in range(n_ids):
                facts.append(F(f"w_{wid}", "who", cand, fld, val, "", cand))
                wid += 1
    return ledger.LedgerCase(CASE_ID, "K1", list(CANDIDATES), facts, {f.id for f in facts}, {"model": "synthetic-engine", "source_format": "enable-md"})


THINKING_A = """We need to produce the integrated report. Determine predicted_diagnosis.
Panel: mk1 positive (p_1), mk4 positive (p_4), mk2 positive (p_2), mk3 positive (p_3), mk5 weak (p_5), mk6 positive (p_6), mk7 strong (p_7), mk8 negative (p_8), mk9 positive (p_9).
Morphology: shape_c positive (p_19), shape_e positive (p_21), shape_g positive (p_23), shape_h positive (p_24); no shape_f (p_22).
Molecular: ig mutated (p_54), GENE21 variant positive (p_46), GENE27 variant positive (p_52), GENE28 variant negative (p_53).
Cytogenetics: del(3q) positive (p_55), del(7p) negative (p_57).
This fits K1 (w_62): mk1 and mk4 positive with shape_g forms. Codes come from w_63 and w_64.
Thus predicted_diagnosis: K1. Now produce the sections with citations and return the JSON only."""

THINKING_B = """We need the differential across K1..K8 with verdicts, supporting and contradicting ids, and the reference criteria.
K1 fits: mk1 positive (p_1), mk4 positive (p_4), shape_g forms (p_23), del(3q) (p_55). K2 needs mk10 positive but mk10 is negative (p_10).
K3 needs GENE05 variant and shape_i; GENE05 variant is negative (p_30) and shape_i was not mentioned (p_25). K4 needs marker_x present; it is absent (c_109).
K5 needs mk14, which was not performed (p_14). K6 and K7 need shape_f or shape_i; shape_f is negative (p_22). K8 needs mk1 negative; mk1 is positive (p_1).
Favoured: K1. Discriminators: mk1 with mk4 and shape_g; mk10 negativity against K2; GENE05 negativity against K3."""


def build_trace() -> ledger.LedgerTrace:
    S, G = ledger.Section, ledger.Segment
    sections = [
        S("Codes:", [G("Code A: 9100/3 K1 category; Code B: 2A81.0 K1 category", ["w_63", "w_64"])]),
        S("Summary of diagnosis:", [G("Summary: ig mutated; del(3q) positive; GENE21 variant positive; GENE27 variant positive; GENE28 variant not detected",
                                      ["p_54", "p_55", "p_46", "p_52", "p_53"]),
                                    G("Additional comments: None", [])]),
        S("Panel:", [G("mk1 positive; mk4 positive; mk2 positive; mk3 positive; mk5 weak; mk6 positive; mk7 strong; mk8 negative; mk9 positive; mk10 negative",
                       ["p_1", "p_4", "p_2", "p_3", "p_5", "p_6", "p_7", "p_8", "p_9", "p_10"])]),
        S("Morphology:", [G("Small mature forms with shape_g and occasional shape_c and shape_e forms; shape_h forms present; no shape_f",
                            ["p_19", "p_21", "p_23", "p_24", "p_22"])]),
        S("Molecular:", [G("ig mutated; GENE21 variant positive; GENE27 variant positive; GENE28 variant negative", ["p_54", "p_46", "p_52", "p_53"])]),
        S("Cytogenetics:", [G("del(3q) positive; del(7p) negative", ["p_55", "p_57"])]),
    ]
    report = ledger.Report("K1", sections, "K1", False, "citation_contract_warning", [{"section": "Summary of diagnosis", "text": "Diagnosis: K1"}])
    key = [("panel", "mk1 positive", ["p_1"]), ("panel", "mk4 positive", ["p_4"]), ("panel", "mk6 positive", ["p_6"]), ("panel", "mk7 strong", ["p_7"]),
           ("panel", "mk8 negative", ["p_8"]), ("panel", "mk9 positive", ["p_9"]), ("panel", "mk10 negative", ["p_10"]), ("panel", "mk12 weak", ["p_12"]),
           ("morphology", "shape_c forms present", ["p_19"]), ("morphology", "shape_e forms present", ["p_21"]), ("morphology", "shape_g forms present", ["p_23"]),
           ("morphology", "shape_h forms present", ["p_24"]), ("molecular", "ig mutated", ["p_54"]), ("molecular", "GENE21 variant positive", ["p_46"]),
           ("molecular", "GENE27 variant positive", ["p_52"]), ("cytogenetics", "del(3q) present", ["p_55"]), ("molecular", "GENE05 variant negative", ["p_30"]),
           ("clinical_context", "level_d 97.5", ["c_107"]), ("clinical_context", "level_e 90.5", ["c_108"]), ("clinical_context", "marker_y present", ["c_110"]),
           ("clinical_context", "marker_z absent", ["c_111"])]
    D, C = ledger.DifferentialEntry, ledger.Criterion
    differential = [
        D("K1", "favoured", ["p_1", "p_2", "p_3", "p_4", "p_6", "p_7", "p_9", "p_23", "p_21", "p_55"], ["p_8"],
          "The panel (mk1, mk4, mk6, mk7) and morphology (shape_g forms with occasional shape_c) fit K1, supported by ig mutation and del(3q).",
          [C("mk1 positivity", "met", ["w_62", "p_1"]), C("mk4 positivity", "met", ["w_62", "p_4"]), C("shape_g forms", "met", ["w_62", "p_23"]),
           C("del(3q)", "met", ["w_62", "p_55"])]),
        D("K2", "unlikely", [], ["p_10"], "mk10 is negative, which K2 requires positive.", [C("mk10 positive with shape_c negative", "not_met", ["w_70", "p_10"])]),
        D("K3", "excluded", [], ["p_30", "p_25"], "GENE05 variant negative and no shape_i forms described.", [C("GENE05 variant detected and shape_i positive", "not_met", ["w_75", "p_30", "p_25"])]),
        D("K4", "unlikely", [], ["c_109", "p_4"], "marker_x absent and mk4 positive argue against K4.", [C("marker_x present; mk10 negative; mk4 negative", "not_met", ["w_80", "c_109", "p_10", "p_4"])]),
        D("K5", "unlikely", ["p_1"], ["p_55"], "mk14 was not performed; del(3q) is more typical of K1.", [C("mk1 positive; mk14 positive", "not_assessable", ["w_87", "p_1", "p_14"])]),
        D("K6", "excluded", [], ["p_22", "p_30"], "shape_f negative.", [C("shape_f positive; GENE05 variant not detected", "not_met", ["w_92", "p_22", "p_30"])]),
        D("K7", "excluded", [], ["p_25", "p_30"], "No shape_i forms described.", [C("shape_i positive; GENE05 variant not detected", "not_met", ["w_97", "p_25", "p_30"])]),
        D("K8", "excluded", [], ["p_1", "c_109"], "mk1 positive and marker_x absent are inconsistent with K8.", [C("mk1 negative; mk4 positive; shape_g positive; marker_x present", "not_met", ["w_102", "p_1"])]),
    ]
    rationale = ledger.Rationale("K1", "high", [{"modality": m, "description": d, "ids": ids} for m, d, ids in key], differential,
                                 [{"text": "mk1 with mk4 and shape_g forms favour K1", "ids": ["p_1", "p_4", "p_23"]},
                                  {"text": "mk10 negativity excludes K2", "ids": ["p_10"]},
                                  {"text": "GENE05 variant negative excludes K3", "ids": ["p_30"]}],
                                 ["mk14 was not performed, so K5 cannot be fully excluded", "shape_c forms could indicate progression"],
                                 ["mk10 positivity would support K2", "GENE05 variant positivity would support K3", "mk1 negativity would support K8"], THINKING_B)
    ablation = ledger.Ablation(["p_1", "p_4", "p_23", "p_55", "p_57"], "K1", "K1", False)
    return ledger.LedgerTrace(THINKING_A, report, rationale, ablation, {"model": "synthetic-engine", "source_format": "enable-md"})


AUDIT_LINES = ["PASS Delivered diagnosis matches ground truth — K1 vs K1", "FAIL Report contract valid (no engine warnings) — citation_contract_warning",
               "FAIL Nothing informative deleted by post-processing — 1 segment(s) dropped", "FAIL Thinking considered more than one diagnosis",
               "FAIL Stated discriminators are load-bearing (diagnosis changes without them) — K1 -> K1"]


def artefact_text() -> str:
    return render_artefact(build_case(), build_trace(), repeat=1, model="synthetic-engine", audit_lines=AUDIT_LINES)


def copied_text(md: str | None = None) -> str:
    """The artefact as a browser copy of the rendered page: no `#` marks, tab tables, no fences, no bold."""
    md = md if md is not None else artefact_text()
    out: list[str] = []
    for line in md.split("\n"):
        if line.startswith("```"):
            continue
        if re.match(r"^#{1,3} ", line):
            line = re.sub(r"^#{1,3} ", "", line)
        if re.match(r"^\|\s*-{3,}", line):
            continue
        if line.startswith("|"):
            line = "\t".join(c.strip() for c in line.strip().strip("|").split("|"))
        line = line.replace("**", "")
        line = re.sub(r"^- (Case:|Model:|Facts:)", r"\1", line)
        line = re.sub(r"`\[(.*?)\]`", r"[\1]", line)
        line = line.replace("`", "")
        if line.startswith("- Discriminator:") or line.startswith("- Unresolved:") or line.startswith("- Would change"):
            line = line[2:]
        if re.match(r"^- Summary of diagnosis: ", line):
            line = line[2:]
        out.append(line)
    return "\n".join(out)
