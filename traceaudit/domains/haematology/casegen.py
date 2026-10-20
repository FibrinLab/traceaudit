"""Synthetic case generation (spec 14): structured truth -> SIHMDS-style reports -> validation.

Dev-time tool; also used to build the packaged 6-case sample. Standard library only.
"""
from __future__ import annotations

import json
import random
from dataclasses import dataclass
from pathlib import Path

from ... import __version__
from ... import extract
from ... import lexicon as lex_mod
from ...lexicon import Lexicon
from ...schema import Case, Flags, Provenance, Review

PRIORS_PATH = Path(__file__).with_name("priors.json")

# ----------------------------------------------------------------------------- priors

DEFAULT_PRIORS = {
    "subtypes": {"MZL": {"SMZL": 0.45, "NMZL": 0.25, "EMZL": 0.30}, "LPL": {"WM": 0.8, None: 0.2}},
    "demographics": {
        "CLL_SLL": {"age": [72, 9], "male": 0.6}, "MCL": {"age": [68, 8], "male": 0.72}, "FL": {"age": [63, 10], "male": 0.5},
        "HCL": {"age": [58, 10], "male": 0.8}, "LPL": {"age": [70, 9], "male": 0.6}, "MZL": {"age": [66, 10], "male": 0.5},
    },
    # explicit P(pos) for `var` cells and overrides; pos cells default 0.95, neg cells 0.05
    "var_prob": {
        "CLL_SLL": {"CD38": 0.35, "CD11c": 0.3, "CD25": 0.3, "del_13q": 0.55, "trisomy_12": 0.15, "del_11q": 0.15, "del_17p": 0.08,
                    "TP53_mut": 0.1, "IGHV_unmutated": 0.45, "NOTCH1_mut": 0.1, "SF3B1_mut": 0.1, "lymphadenopathy": 0.5,
                    "splenomegaly": 0.3, "cytopenias": 0.2, "IgM_paraprotein": 0.05, "prolymphocytes_increased": 0.1},
        "MCL": {"SOX11": 0.9, "del_17p": 0.15, "TP53_mut": 0.2, "IGHV_unmutated": 0.7, "lymphocytosis": 0.5, "splenomegaly": 0.4,
                "cytopenias": 0.25, "blastoid": 0.15, "Ki67_high": 0.3, "prominent_nucleoli": 0.1, "mantle_zone_pattern": 0.3,
                "extranodal_site": 0.2, "CCND2_rearr": 0.0},
        "FL": {"t_14_18_BCL2": 0.85, "CD23": 0.3, "EZH2_mut": 0.25, "CREBBP_mut": 0.6, "KMT2D_mut": 0.7, "lymphocytosis": 0.05,
               "cytopenias": 0.1, "splenomegaly": 0.1, "del_17p": 0.05, "TP53_mut": 0.05, "extranodal_site": 0.1},
        "HCL": {"BRAF_V600E": 0.97, "cyclin_D1": 0.3, "intrasinusoidal": 0.5, "del_17p": 0.0, "lymphocytosis": 0.0},
        "LPL": {"MYD88_L265P": 0.9, "CXCR4_mut": 0.35, "CD200": 0.4, "FMC7": 0.5, "IgD": 0.3, "lymphocytosis": 0.1, "splenomegaly": 0.3,
                "lymphadenopathy": 0.3, "cytopenias": 0.5, "hyperviscosity": 0.3, "del_7q": 0.05, "dry_tap_fibrosis": 0.1,
                "del_17p": 0.05, "TP53_mut": 0.05, "CD43": 0.3},
        "MZL": {"CD5": 0.1, "CD200": 0.3, "CD11c": 0.4, "CD43": 0.3, "IgD": 0.5, "del_7q": 0.3, "trisomy_12": 0.05, "KLF2_mut": 0.25,
                "NOTCH2_mut": 0.2, "TNFAIP3_mut": 0.2, "MYD88_L265P": 0.05, "t_11_18_MALT1": 0.25, "t_1_14_BCL10": 0.05,
                "t_14_18_MALT1": 0.05, "IgM_paraprotein": 0.2, "CD138_plasma_cells": 0.25, "lymphoplasmacytic_cells": 0.2,
                "lymphocytosis": 0.4, "splenomegaly": 0.7, "lymphadenopathy": 0.3, "cytopenias": 0.3, "villous_lymphocytes": 0.6,
                "monocytoid_cells": 0.5, "intrasinusoidal": 0.6, "extranodal_site": 0.5, "CD103": 0.05, "EZH2_mut": 0.0,
                "CREBBP_mut": 0.0, "KMT2D_mut": 0.1, "IGHV_unmutated": 0.3},
    },
    "discordance_whitelist": {
        "CLL_SLL": [["CD23", "neg"], ["CD200", "neg"], ["FMC7", "pos"]],
        "MCL": [["CD23", "pos"], ["SOX11", "neg"], ["CD5", "neg"]],
        "FL": [["CD10", "neg"], ["BCL6", "neg"]],
        "HCL": [["CD25", "neg"], ["CD123", "neg"], ["annexin_A1", "neg"]],
        "LPL": [["MYD88_L265P", "neg"], ["CD5", "pos"]],
        "MZL": [["CD5", "pos"], ["CD23", "pos"]],
    },
    "p_discordant": 0.10,
    "p_incomplete": 0.05,
}


def load_priors(path: str | Path | None = None) -> dict:
    p = Path(path) if path else PRIORS_PATH
    if p.exists():
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    return DEFAULT_PRIORS


# ----------------------------------------------------------------------------- panels

FLOW_CORE = ["CD19", "CD5", "CD10", "CD20_dim", "CD22", "CD23", "CD38", "CD43", "CD79b", "CD200", "FMC7", "sIg_dim", "light_chain_restricted"]
FLOW_HCL = ["CD11c", "CD25", "CD103", "CD123"]
PANELS = {
    "CLL_SLL": {
        "specimen": "pb_bm", "clinical": ["lymphocytosis", "lymphadenopathy", "splenomegaly", "cytopenias", "monocytopenia", "B_symptoms"],
        "morphology": ["smudge_cells", "prolymphocytes_increased"], "ihc": ["cyclin_D1", "LEF1"],
        "flow": FLOW_CORE + ["IgD"], "cytogenetics": ["del_13q", "trisomy_12", "del_11q", "del_17p", "t_11_14"],
        "molecular": ["IGHV_unmutated", "TP53_mut", "NOTCH1_mut", "SF3B1_mut"],
    },
    "MCL": {
        "specimen": "node_bm", "clinical": ["lymphocytosis", "lymphadenopathy", "splenomegaly", "cytopenias", "B_symptoms", "extranodal_site"],
        "morphology": ["mantle_zone_pattern", "blastoid", "prominent_nucleoli"], "ihc": ["cyclin_D1", "SOX11", "LEF1", "Ki67_high"],
        "flow": FLOW_CORE + ["IgD"], "cytogenetics": ["t_11_14", "del_17p"], "molecular": ["TP53_mut", "IGHV_unmutated"],
    },
    "FL": {
        "specimen": "node", "clinical": ["lymphocytosis", "lymphadenopathy", "splenomegaly", "cytopenias", "B_symptoms", "extranodal_site"],
        "morphology": ["follicular_pattern", "centrocytes"], "ihc": ["BCL6", "BCL2", "cyclin_D1", "Ki67_high"],
        "flow": FLOW_CORE, "cytogenetics": ["t_14_18_BCL2", "t_11_14", "del_17p"], "molecular": ["EZH2_mut", "CREBBP_mut", "KMT2D_mut", "TP53_mut"],
    },
    "HCL": {
        "specimen": "pb_bm", "clinical": ["lymphocytosis", "splenomegaly", "lymphadenopathy", "cytopenias", "monocytopenia", "B_symptoms"],
        "morphology": ["hairy_cells", "dry_tap_fibrosis", "interstitial_fried_egg", "intrasinusoidal"], "ihc": ["annexin_A1", "cyclin_D1"],
        "flow": FLOW_CORE + FLOW_HCL, "cytogenetics": ["complex_karyotype"], "molecular": ["BRAF_V600E", "MAP2K1_mut"],
    },
    "LPL": {
        "specimen": "pb_bm", "clinical": ["lymphocytosis", "IgM_paraprotein", "hyperviscosity", "lymphadenopathy", "splenomegaly", "cytopenias", "monocytopenia"],
        "morphology": ["lymphoplasmacytic_cells", "mast_cell_increase", "dry_tap_fibrosis"], "ihc": ["CD138_plasma_cells", "cyclin_D1"],
        "flow": FLOW_CORE + ["IgD"], "cytogenetics": ["t_11_14", "del_17p", "del_7q"], "molecular": ["MYD88_L265P", "CXCR4_mut", "TP53_mut"],
    },
    "MZL": {
        "SMZL": {"specimen": "pb_bm", "clinical": ["lymphocytosis", "splenomegaly", "lymphadenopathy", "cytopenias", "monocytopenia", "IgM_paraprotein"],
                 "morphology": ["villous_lymphocytes", "intrasinusoidal", "lymphoplasmacytic_cells"], "ihc": ["cyclin_D1", "annexin_A1", "CD138_plasma_cells"],
                 "flow": FLOW_CORE + ["IgD", "CD11c", "CD103"], "cytogenetics": ["del_7q", "t_11_14", "t_14_18_BCL2", "trisomy_12"],
                 "molecular": ["KLF2_mut", "NOTCH2_mut", "MYD88_L265P", "BRAF_V600E", "IGHV_unmutated"]},
        "NMZL": {"specimen": "node", "clinical": ["lymphocytosis", "lymphadenopathy", "splenomegaly", "cytopenias", "B_symptoms", "IgM_paraprotein"],
                 "morphology": ["monocytoid_cells", "lymphoplasmacytic_cells"], "ihc": ["cyclin_D1", "BCL6", "CD138_plasma_cells"],
                 "flow": FLOW_CORE + ["IgD", "CD11c"], "cytogenetics": ["t_11_14", "t_14_18_BCL2", "trisomy_12"],
                 "molecular": ["MYD88_L265P", "KMT2D_mut", "TNFAIP3_mut"]},
        "EMZL": {"specimen": "extranodal", "clinical": ["extranodal_site", "lymphadenopathy", "splenomegaly", "cytopenias", "B_symptoms", "lymphocytosis"],
                 "morphology": ["monocytoid_cells", "lymphoplasmacytic_cells"], "ihc": ["cyclin_D1", "BCL6", "CD138_plasma_cells"],
                 "flow": FLOW_CORE + ["CD11c"], "cytogenetics": ["t_11_18_MALT1", "t_1_14_BCL10", "t_14_18_MALT1", "t_11_14", "t_14_18_BCL2"],
                 "molecular": ["TNFAIP3_mut", "MYD88_L265P", "KMT2D_mut"]},
    },
}

CASE_PREFIX = {"CLL_SLL": "CLL", "MCL": "MCL", "FL": "FL", "HCL": "HCL", "LPL": "LPL", "MZL": "MZL"}


@dataclass
class Draft:
    case: Case
    numbers: dict


# ----------------------------------------------------------------------------- truth sampling

def _p_pos(entity: str, subtype: str | None, fid: str, lx: Lexicon, priors: dict) -> float:
    vp = priors["var_prob"].get(entity, {})
    if fid in vp:
        return vp[fid]
    exp = lx.expected(fid, entity)
    if exp == "pos":
        return 0.98
    if exp == "neg":
        return 0.02
    return 0.3


def sample_truth(entity: str, rng: random.Random, lx: Lexicon, priors: dict) -> tuple[dict[str, str], str | None, dict, Flags]:
    subtype = None
    if entity in priors["subtypes"]:
        opts = priors["subtypes"][entity]
        keys = list(opts)
        subtype = rng.choices(keys, weights=[opts[k] for k in keys])[0]
        subtype = None if subtype in (None, "null", "None") else subtype
    panel = PANELS[entity][subtype] if entity == "MZL" else PANELS[entity]
    truth: dict[str, str] = {}
    for section in ("clinical", "morphology", "ihc", "flow", "cytogenetics", "molecular"):
        for fid in panel[section]:
            p = _p_pos(entity, subtype, fid, lx, priors)
            if subtype == "EMZL" and fid == "extranodal_site":
                p = 1.0
            if subtype == "SMZL" and fid == "splenomegaly":
                p = 0.95
            truth[fid] = "pos" if rng.random() < p else "neg"
    truth["CD19"] = "pos"
    truth["light_chain_restricted"] = "pos"
    flags = Flags()
    _coherence_repair(entity, subtype, truth, rng)
    # discordance
    if rng.random() < priors["p_discordant"]:
        fid, pol = rng.choice(priors["discordance_whitelist"][entity])
        if fid in truth and truth[fid] != pol:
            truth[fid] = pol
            flags.discordant = True
            flags.atypical_features.append(f"{fid}:{pol}")
            _coherence_repair(entity, subtype, truth, rng, keep={fid})
    return truth, subtype, panel, flags


def _coherence_repair(entity: str, subtype: str | None, truth: dict[str, str], rng: random.Random, keep: set | None = None) -> None:
    keep = keep or set()

    def setv(fid, val):
        if fid in truth and fid not in keep:
            truth[fid] = val

    # defining markers are coherent with the entity unless deliberately kept atypical
    if entity != "MCL":
        setv("t_11_14", "neg")
        setv("SOX11", "neg")
        if entity != "HCL":
            setv("cyclin_D1", "neg")
    if entity != "FL":
        setv("t_14_18_BCL2", "neg")
        setv("CD10", "neg")
        setv("BCL6", "neg")
    if entity != "HCL":
        setv("BRAF_V600E", "neg")
        setv("annexin_A1", "neg")
        setv("CD103", "neg")
        setv("CD123", "neg")
        setv("hairy_cells", "neg")
        setv("interstitial_fried_egg", "neg")
    if entity not in ("LPL", "MZL"):
        setv("MYD88_L265P", "neg")
    if entity not in ("LPL", "MZL", "CLL_SLL"):
        setv("IgM_paraprotein", "neg")
    if truth.get("t_11_14") == "pos":
        setv("cyclin_D1", "pos")
    if entity == "MCL":
        if truth.get("cyclin_D1") == "neg" and "cyclin_D1" not in keep:
            truth["cyclin_D1"] = "pos"
        if truth.get("cyclin_D1") == "pos" and truth.get("t_11_14") == "neg" and "t_11_14" not in keep:
            truth["t_11_14"] = "pos"
        if truth.get("blastoid") == "pos":
            setv("Ki67_high", "pos")
    if entity == "HCL":
        setv("hairy_cells", "pos")
        if truth.get("lymphocytosis") == "pos":
            setv("lymphocytosis", "neg")
    if entity == "LPL":
        if truth.get("IgM_paraprotein") == "neg" and subtype == "WM" and "IgM_paraprotein" not in keep:
            truth["IgM_paraprotein"] = "pos"
        setv("lymphoplasmacytic_cells", "pos")
    if entity == "FL":
        setv("follicular_pattern", "pos")
        if truth.get("t_14_18_BCL2") == "pos":
            setv("BCL2", "pos")
    if entity == "CLL_SLL":
        if truth.get("lymphocytosis") == "neg" and truth.get("lymphadenopathy") == "neg" and truth.get("splenomegaly") == "neg" \
                and truth.get("cytopenias") == "neg" and "lymphocytosis" not in keep:
            truth["lymphocytosis"] = "pos"
    if entity == "MZL" and subtype == "SMZL":
        if truth.get("villous_lymphocytes") == "neg" and truth.get("intrasinusoidal") == "neg":
            setv("villous_lymphocytes", "pos")
    # monocytopenia only with HCL (or rarely otherwise)
    if entity != "HCL" and truth.get("monocytopenia") == "pos" and rng.random() < 0.9:
        setv("monocytopenia", "neg")
    if entity == "HCL":
        setv("monocytopenia", "pos")
        setv("cytopenias", "pos")


# ----------------------------------------------------------------------------- numbers

def sample_numbers(entity: str, truth: dict[str, str], rng: random.Random, priors: dict) -> dict:
    d = priors["demographics"][entity]
    age = int(min(88, max(40, rng.gauss(d["age"][0], d["age"][1]))))
    sex = "man" if rng.random() < d["male"] else "woman"
    n: dict = {"age": age, "sex": sex}
    if truth.get("lymphocytosis") == "pos":
        n["clonal_b"] = round(5.5 * (120 / 5.5) ** rng.random(), 1)
    else:
        n["clonal_b"] = round(rng.uniform(0.3, 4.9), 1)
    wbc_extra = rng.uniform(3.5, 7.5)
    n["wbc"] = round(n["clonal_b"] + wbc_extra, 1)
    if truth.get("cytopenias") == "pos":
        which = rng.choice(["anaemia", "thrombocytopenia", "pancytopenia", "neutropenia"])
        n["hb"] = rng.randint(78, 99) if which in ("anaemia", "pancytopenia") else rng.randint(118, 152)
        n["plt"] = rng.randint(40, 95) if which in ("thrombocytopenia", "pancytopenia") else rng.randint(160, 320)
        n["neut"] = round(rng.uniform(0.4, 0.95), 2) if which in ("neutropenia", "pancytopenia") else round(rng.uniform(1.8, 5.5), 1)
    else:
        n["hb"] = rng.randint(120, 158)
        n["plt"] = rng.randint(160, 340)
        n["neut"] = round(rng.uniform(1.9, 6.0), 1)
    n["mono"] = round(rng.uniform(0.0, 0.15), 2) if truth.get("monocytopenia") == "pos" else round(rng.uniform(0.3, 0.9), 2)
    n["spleen_cm"] = rng.randint(14, 24)
    n["node_cm"] = round(rng.uniform(1.5, 4.5), 1)
    n["igm_gl"] = rng.randint(8, 48)
    n["ki67"] = rng.randint(35, 80) if truth.get("Ki67_high") == "pos" else rng.randint(5, 20)
    n["prolymph"] = rng.randint(11, 30) if truth.get("prolymphocytes_increased") == "pos" else rng.randint(1, 5)
    n["vaf"] = rng.randint(12, 48)
    n["ighv_identity"] = round(rng.uniform(98.0, 100.0), 1) if truth.get("IGHV_unmutated") == "pos" else round(rng.uniform(90.0, 97.5), 1)
    n["b_percent"] = rng.randint(55, 92)
    n["specimen_no"] = f"H26-{rng.randint(1000, 9999):04d}"
    n["date"] = f"{rng.randint(1, 28):02d} {rng.choice(['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Sep', 'Oct', 'Nov'])} 2026"
    n["reporter"] = rng.choice(["AO/SK", "JM/RP", "LT/AO", "SK/DB", "RP/LT"])
    n["light_chain"] = rng.choice(["kappa", "lambda"])
    n["site"] = rng.choice(["gastric biopsy", "parotid", "ocular adnexa", "lung nodule", "thyroid mass"])
    return n


# ----------------------------------------------------------------------------- rendering

def _pol(truth, fid):
    return truth.get(fid)


def _render_marker(fid: str, pol: str, rng: random.Random, style: str, lx: Lexicon) -> str:
    alias = lx.aliases(fid)[0]
    if fid == "CD20_dim":
        return "CD20 dim" if pol == "pos" else rng.choice(["CD20 bright", "CD20 moderate"])
    if fid == "sIg_dim":
        return ""  # handled in sentence
    if style == "symbol":
        return f"{alias}{'+' if pol == 'pos' else '-'}"
    if style == "word":
        return f"{alias} {'positive' if pol == 'pos' else 'negative'}"
    return f"{alias}{'+' if pol == 'pos' else '-'}"


def _join(items: list[str]) -> str:
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " and " + items[-1]


def render_flow(entity, subtype, truth, panel, n, rng, lx) -> str:
    specimen = {"pb_bm": "peripheral blood", "node_bm": "peripheral blood", "node": "lymph node (disaggregated tissue)", "extranodal": "tissue biopsy (disaggregated)"}[panel["specimen"]]
    out = [f"Flow cytometry, {specimen}. Gating on CD19+ events ({n['b_percent']}% of lymphocytes)."]
    sig = "dim" if truth.get("sIg_dim") == "pos" else rng.choice(["moderate-intensity", "bright"])
    out.append(rng.choice([
        f"A clonal B-cell population is present, {n['light_chain']} light-chain restricted, with {sig} surface immunoglobulin.",
        f"Clonal B cells are identified ({n['light_chain']} restricted) showing {sig} surface Ig.",
    ]))
    markers = [f for f in panel["flow"] if f not in ("CD19", "sIg_dim", "light_chain_restricted")]
    style = rng.choice(["symbol", "symbol", "word", "lists"])
    if style == "lists":
        pos = [lx.aliases(f)[0] for f in markers if truth[f] == "pos" and f != "CD20_dim"]
        neg = [lx.aliases(f)[0] for f in markers if truth[f] == "neg" and f != "CD20_dim"]
        cd20 = _render_marker("CD20_dim", truth["CD20_dim"], rng, style, lx)
        out.append(f"The clonal cells are positive for {_join(pos)} and negative for {_join(neg)}; {cd20}.")
    else:
        parts = [_render_marker(f, truth[f], rng, style, lx) for f in markers]
        out.append("Phenotype: " + ", ".join(parts) + ".")
    out.append(f"Reported by {n['reporter']}, {n['date']}. Specimen {n['specimen_no']}.")
    return " ".join(out)


def render_clinical(entity, subtype, truth, panel, n, rng, lx) -> str:
    out = [f"{n['age']}-year-old {n['sex']} referred for assessment of a lymphoproliferative disorder."]
    cl = panel["clinical"]
    if "extranodal_site" in cl:
        out.append(f"Presentation with an extranodal mass ({n['site']})." if truth["extranodal_site"] == "pos" else "No extranodal disease.")
    if "lymphadenopathy" in cl:
        out.append(f"Cervical and axillary lymphadenopathy (nodes up to {n['node_cm']} cm)." if truth["lymphadenopathy"] == "pos" else "No lymphadenopathy.")
    if "splenomegaly" in cl:
        out.append(f"Splenomegaly (spleen {n['spleen_cm']} cm on ultrasound)." if truth["splenomegaly"] == "pos" else "No splenomegaly.")
    if "B_symptoms" in cl:
        out.append("B symptoms (night sweats and weight loss)." if truth["B_symptoms"] == "pos" else "No B symptoms.")
    if "hyperviscosity" in cl:
        out.append("Symptoms of hyperviscosity (blurred vision, epistaxis)." if truth["hyperviscosity"] == "pos" else "No features of hyperviscosity.")
    fbc = f"Full blood count: Hb {n['hb']} g/L, WBC {n['wbc']} x10^9/L, neutrophils {n['neut']} x10^9/L, platelets {n['plt']} x10^9/L"
    if "cytopenias" in cl:
        fbc += "; pancytopenia." if (n['hb'] < 100 and n['plt'] < 100) else ("; cytopenias noted." if truth["cytopenias"] == "pos" else "; no cytopenias.")
    else:
        fbc += "."
    out.append(fbc)
    if "monocytopenia" in cl:
        out.append(f"Monocytes {n['mono']} x10^9/L.")
    if "lymphocytosis" in cl:
        out.append(f"Clonal B-cell count {n['clonal_b']} x10^9/L.")
    if "IgM_paraprotein" in cl:
        out.append(f"Serum electrophoresis: IgM {n['light_chain']} paraprotein {n['igm_gl']} g/L." if truth["IgM_paraprotein"] == "pos"
                   else "Serum electrophoresis: no paraprotein detected.")
    return " ".join(out)


def render_morphology(entity, subtype, truth, panel, n, rng, lx) -> str:
    spec = panel["specimen"]
    head = {"pb_bm": "Peripheral blood film and bone marrow aspirate/trephine.", "node_bm": "Lymph node core biopsy and peripheral blood film.",
            "node": "Lymph node excision biopsy.", "extranodal": f"Biopsy of {n['site']}."}[spec]
    out = [head]
    for fid in panel["morphology"]:
        f = lx.findings[fid]
        pol = truth[fid]
        if fid == "prolymphocytes_increased":
            out.append(f"Prolymphocytes {n['prolymph']}%.")
            continue
        out.append(f["pos_text"] if pol == "pos" else f["neg_text"])
    ihc = panel.get("ihc", [])
    if ihc:
        style = rng.choice(["symbol", "word", "lists"])
        if style == "lists":
            pos = [lx.aliases(f)[0] for f in ihc if truth[f] == "pos" and f != "Ki67_high"]
            neg = [lx.aliases(f)[0] for f in ihc if truth[f] == "neg" and f != "Ki67_high"]
            s = "Immunohistochemistry: "
            if pos:
                s += f"positive for {_join(pos)}"
            if neg:
                s += (" and " if pos else "") + f"negative for {_join(neg)}"
            out.append(s + ".")
        else:
            parts = [_render_marker(f, truth[f], rng, style, lx) for f in ihc if f != "Ki67_high"]
            out.append("Immunohistochemistry: " + ", ".join(parts) + ".")
        if "Ki67_high" in ihc:
            out.append(f"Ki-67 approximately {n['ki67']}%.")
    out.append(f"Reported by {n['reporter']}, {n['date']}.")
    return " ".join(out)


def render_cytogenetics(entity, subtype, truth, panel, n, rng, lx) -> str:
    out = ["Interphase FISH on the clonal B-cell population." if panel["cytogenetics"] and panel["cytogenetics"] != ["complex_karyotype"]
           else "Conventional karyotype."]
    for fid in panel["cytogenetics"]:
        f = lx.findings[fid]
        out.append(f["pos_text"] if truth[fid] == "pos" else f["neg_text"])
    out.append(f"Reported by {n['reporter']}, {n['date']}.")
    return " ".join(out)


def render_molecular(entity, subtype, truth, panel, n, rng, lx) -> str:
    out = ["Targeted NGS panel (lymphoid)."]
    for fid in panel["molecular"]:
        f = lx.findings[fid]
        if fid == "IGHV_unmutated":
            out.append(f"IGHV unmutated ({n['ighv_identity']}% germline identity)." if truth[fid] == "pos"
                       else f"IGHV mutated ({n['ighv_identity']}% germline identity).")
            continue
        txt = f["pos_text"] if truth[fid] == "pos" else f["neg_text"]
        txt = txt.replace("VAF 28%", f"VAF {n['vaf']}%").replace("VAF 34%", f"VAF {n['vaf']}%").replace("VAF 41%", f"VAF {n['vaf']}%")
        out.append(txt)
    out.append(f"Reported by {n['reporter']}, {n['date']}.")
    return " ".join(out)


def render_reports(entity, subtype, truth, panel, n, rng, lx) -> dict[str, str]:
    return {
        "clinical": render_clinical(entity, subtype, truth, panel, n, rng, lx),
        "morphology": render_morphology(entity, subtype, truth, panel, n, rng, lx),
        "flow_cytometry": render_flow(entity, subtype, truth, panel, n, rng, lx),
        "cytogenetics": render_cytogenetics(entity, subtype, truth, panel, n, rng, lx),
        "molecular": render_molecular(entity, subtype, truth, panel, n, rng, lx),
    }


# ----------------------------------------------------------------------------- driver

def generate_case(entity: str, index: int, seed: int, lx: Lexicon | None = None, priors: dict | None = None,
                  force_incomplete: str | None = None) -> Case:
    lx = lx or lex_mod.load(Path(__file__).with_name("lexicon.json"))
    priors = priors or load_priors()
    rng = random.Random(f"{seed}:{entity}:{index}")
    truth, subtype, panel, flags = sample_truth(entity, rng, lx, priors)
    n = sample_numbers(entity, truth, rng, priors)
    reports = render_reports(entity, subtype, truth, panel, n, rng, lx)
    drop = force_incomplete
    if drop is None and rng.random() < priors["p_incomplete"]:
        drop = rng.choice(["cytogenetics", "molecular"])
    if drop:
        for fid in panel[drop]:
            truth.pop(fid, None)
        reports[drop] = ""
        flags.incomplete = True
        flags.missing_modalities = [drop]
    case = Case(case_id=f"{CASE_PREFIX[entity]}-{index:03d}", entity=entity, subtype=subtype, reports=reports, truth=truth,
                flags=flags, provenance=Provenance(generator_version=__version__, template_id=f"{entity.lower()}-{panel['specimen']}", seed=seed),
                review=Review(status="draft"))
    # the generator's own truth is what the extractor reads back; C1 is checked, not assumed
    found = extract.findings(case.render(), lx)
    if found != truth:
        extra = {k: v for k, v in found.items() if k not in truth}
        missing = {k: v for k, v in truth.items() if k not in found}
        diff = {k: (truth[k], found[k]) for k in truth if k in found and truth[k] != found[k]}
        raise RuntimeError(f"{case.case_id}: template/extractor mismatch extra={extra} missing={missing} differ={diff}")
    return case


def generate_set(per_entity: int, seed: int, lx: Lexicon | None = None, priors: dict | None = None,
                 entities: list[str] | None = None) -> list[Case]:
    lx = lx or lex_mod.load(Path(__file__).with_name("lexicon.json"))
    priors = priors or load_priors()
    cases = []
    for ent in entities or list(CASE_PREFIX):
        for i in range(1, per_entity + 1):
            cases.append(generate_case(ent, i, seed, lx, priors))
    return cases


def review_sheet(cases: list[Case]) -> str:
    """CSV with one row per case for haematologist review (spec 14 §5)."""
    import csv
    import io
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["case_id", "entity", "subtype", "flags", "clinical", "morphology", "flow_cytometry", "cytogenetics", "molecular", "truth", "status", "notes"])
    for c in cases:
        w.writerow([c.case_id, c.entity, c.subtype or "", json.dumps(c.flags.to_dict()), c.reports["clinical"], c.reports["morphology"],
                    c.reports["flow_cytometry"], c.reports["cytogenetics"], c.reports["molecular"],
                    "; ".join(f"{k}={v}" for k, v in sorted(c.truth.items())), c.review.status, c.review.notes])
    return buf.getvalue()


def import_review_sheet(cases: list[Case], csv_text: str, reviewer_id: str, date: str) -> list[Case]:
    import csv
    import io
    rows = {r["case_id"]: r for r in csv.DictReader(io.StringIO(csv_text))}
    for c in cases:
        r = rows.get(c.case_id)
        if r and r.get("status") in ("approved", "rejected", "draft"):
            c.review = Review(reviewer_id=reviewer_id, date=date, status=r["status"], notes=r.get("notes", ""))
    return cases


def approve_all(cases: list[Case], reviewer_id: str = "R00", date: str = "1970-01-01", note: str = "auto-approved sample") -> None:
    for c in cases:
        c.review = Review(reviewer_id=reviewer_id, date=date, status="approved", notes=note)
