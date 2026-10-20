"""Builds the haematology lexicon.json (spec 02). Run: python -m traceaudit.domains.haematology.build_lexicon

The JSON file is the artefact the package loads; this script is its editable source.
Clinical content is [DRAFT-CLINICAL] pending haematologist sign-off.
"""
from __future__ import annotations

import json
from pathlib import Path

VERSION = "1.1.0"


def F(id, display, kind, modality, aliases, pos_phrases=(), neg_phrases=(), intensity=False,
      numeric_rule=None, default_polarity=None, pos_text=None, neg_text=None, notes=""):
    return {
        "id": id, "display": display, "kind": kind, "modality": modality,
        "aliases": list(aliases), "pos_phrases": list(pos_phrases), "neg_phrases": list(neg_phrases),
        "intensity": intensity, "numeric_rule": numeric_rule, "default_polarity": default_polarity,
        "pos_text": pos_text, "neg_text": neg_text, "notes": notes,
    }


IMM = "immunophenotype"
CYT = "cytogenetic"
MOL = "molecular"
MOR = "morphology"
CLI = "clinical"

FINDINGS = [
    # --- immunophenotype (flow / IHC)
    F("CD5", "CD5", IMM, "flow_cytometry", ["CD5"]),
    F("CD10", "CD10", IMM, "flow_cytometry", ["CD10", "CALLA"]),
    F("CD11c", "CD11c", IMM, "flow_cytometry", ["CD11c"]),
    F("CD19", "CD19", IMM, "flow_cytometry", ["CD19"], notes="pan-B, neutral"),
    F("CD20_dim", "CD20 dim", IMM, "flow_cytometry", ["CD20"], intensity=True, notes="pos = dim/weak CD20"),
    F("CD22", "CD22", IMM, "flow_cytometry", ["CD22"]),
    F("CD23", "CD23", IMM, "flow_cytometry", ["CD23"]),
    F("CD25", "CD25", IMM, "flow_cytometry", ["CD25"]),
    F("CD38", "CD38", IMM, "flow_cytometry", ["CD38"], notes="prognostic in CLL, not discriminating"),
    F("CD43", "CD43", IMM, "flow_cytometry", ["CD43"]),
    F("CD79b", "CD79b", IMM, "flow_cytometry", ["CD79b"]),
    F("CD103", "CD103", IMM, "flow_cytometry", ["CD103"]),
    F("CD123", "CD123", IMM, "flow_cytometry", ["CD123"]),
    F("CD138_plasma_cells", "CD138+ plasma cell component", IMM, "flow_cytometry",
      ["CD138", "plasma cell component", "plasmacytic component", "CD138-positive plasma cells"]),
    F("CD200", "CD200", IMM, "flow_cytometry", ["CD200"]),
    F("FMC7", "FMC7", IMM, "flow_cytometry", ["FMC7", "FMC-7"]),
    F("sIg_dim", "surface Ig dim", IMM, "flow_cytometry",
      ["surface immunoglobulin", "surface Ig", "sIg", "surface kappa", "surface lambda", "surface light chain",
       "light chain intensity", "surface light-chain"], intensity=True, notes="pos = dim/weak surface Ig"),
    F("IgD", "IgD", IMM, "flow_cytometry", ["IgD", "surface IgD"]),
    F("light_chain_restricted", "light-chain restriction", IMM, "flow_cytometry", [],
      pos_phrases=["kappa restricted", "kappa-restricted", "lambda restricted", "lambda-restricted",
                   "light chain restricted", "light-chain restricted", "light chain restriction",
                   "light-chain restriction", "clonal B-cell population", "clonal B cell population",
                   "monotypic", "kappa light-chain restricted", "lambda light-chain restricted",
                   "kappa light chain restricted", "lambda light chain restricted", "clonal B cells",
                   "clonal B-cells", "monoclonal B-cell population", "monoclonal B cell population"],
      neg_phrases=["polytypic", "no light chain restriction", "no light-chain restriction",
                   "no clonal B-cell population", "no clonal B cell population", "no monoclonal B-cell population"],
      pos_text="A clonal B-cell population is present (light-chain restricted).",
      neg_text="No clonal B-cell population is identified (polytypic light chains)."),
    F("cyclin_D1", "cyclin D1", IMM, "flow_cytometry",
      ["cyclin D1", "cyclin-D1", "cyclinD1", "BCL1", "BCL-1", "CCND1 protein", "CCND1 expression", "CCND1 staining",
       "CCND1 immunohistochemistry", "CCND1 IHC", "CCND1"], notes="IHC; bare CCND1 switched to t_11_14 in FISH context by extract"),
    F("SOX11", "SOX11", IMM, "flow_cytometry", ["SOX11", "SOX-11"]),
    F("LEF1", "LEF1", IMM, "flow_cytometry", ["LEF1", "LEF-1"]),
    F("BCL2", "BCL2 (protein)", IMM, "flow_cytometry",
      ["BCL2 expression", "BCL-2 expression", "BCL2 protein", "BCL-2 protein", "BCL2 staining", "BCL-2 staining",
       "BCL2 IHC", "BCL2 immunohistochemistry", "BCL2", "BCL-2"], notes="neutral; bare BCL2 switched to t_14_18_BCL2 in FISH context by extract"),
    F("BCL6", "BCL6", IMM, "flow_cytometry", ["BCL6", "BCL-6"]),
    F("annexin_A1", "annexin A1", IMM, "flow_cytometry", ["annexin A1", "annexin-A1", "annexin A-1", "ANXA1"]),
    F("TRAP", "TRAP", IMM, "flow_cytometry", ["TRAP", "tartrate-resistant acid phosphatase"], notes="historical"),
    F("Ki67_high", "high proliferation index", IMM, "morphology", ["Ki-67", "Ki67", "MIB-1", "MIB1"],
      pos_phrases=["high proliferation index", "high Ki-67", "high Ki67", "Ki-67 is high", "elevated Ki-67", "proliferation index is high"],
      neg_phrases=["low proliferation index", "low Ki-67", "low Ki67", "Ki-67 is low", "proliferation index is low"],
      numeric_rule={"anchors": ["Ki-67", "Ki67", "MIB-1", "MIB1", "proliferation index", "proliferation fraction"],
                    "fallback_anchors": [], "unit_pattern": "%", "comparator": ">=", "threshold": 30.0},
      pos_text="Ki-67 proliferation index is high (approximately 45%).",
      neg_text="Ki-67 proliferation index is low (approximately 10%)."),
    # --- cytogenetic / FISH
    F("t_11_14", "t(11;14) CCND1::IGH", CYT, "cytogenetics",
      ["t(11;14)(q13;q32)", "t(11;14)", "CCND1::IGH", "IGH::CCND1", "CCND1-IGH", "IGH-CCND1", "CCND1/IGH", "IGH/CCND1",
       "CCND1 rearrangement", "CCND1 translocation", "CCND1 break-apart", "CCND1 fusion", "IGH-CCND1 fusion"],
      pos_text="t(11;14)(q13;q32) CCND1::IGH detected by FISH.",
      neg_text="No t(11;14) CCND1::IGH detected by FISH."),
    F("CCND2_rearr", "CCND2/CCND3 rearrangement", CYT, "cytogenetics",
      ["CCND2 rearrangement", "CCND3 rearrangement", "CCND2 translocation", "t(12;14)", "CCND2::IGK", "CCND2::IGL"],
      pos_text="CCND2 rearrangement detected by FISH.", neg_text="No CCND2 or CCND3 rearrangement detected."),
    F("t_14_18_BCL2", "t(14;18) IGH::BCL2", CYT, "cytogenetics",
      ["t(14;18)(q32;q21)", "t(14;18)", "IGH::BCL2", "BCL2::IGH", "IGH-BCL2", "BCL2-IGH", "IGH/BCL2", "BCL2/IGH",
       "BCL2 rearrangement", "BCL2 translocation", "BCL2 break-apart", "BCL-2 rearrangement", "BCL2 fusion"],
      pos_text="t(14;18)(q32;q21) IGH::BCL2 detected by FISH.",
      neg_text="No t(14;18) IGH::BCL2 detected by FISH."),
    F("del_17p", "del(17p)", CYT, "cytogenetics",
      ["del(17p)", "del(17p13)", "del(17)(p13)", "17p deletion", "deletion of 17p", "TP53 deletion", "loss of 17p", "17p loss",
       "TP53 FISH", "del 17p", "del 17p13"],
      pos_text="del(17p) detected by FISH (TP53 locus).", neg_text="No del(17p) detected by FISH."),
    F("del_13q", "del(13q)", CYT, "cytogenetics",
      ["del(13q)", "del(13q14)", "del(13)(q14)", "13q deletion", "13q14 deletion", "deletion of 13q", "13q14 loss", "del 13q", "del 13q14"],
      pos_phrases=["isolated del(13q)", "sole del(13q)", "isolated del 13q", "sole del 13q", "isolated del(13q14)", "sole del(13q14)",
                   "del(13q) as the sole abnormality", "del 13q as the sole abnormality", "del(13q) alone", "del 13q alone"],
      pos_text="del(13q14) detected by FISH.", neg_text="No del(13q) detected by FISH."),
    F("del_11q", "del(11q)", CYT, "cytogenetics",
      ["del(11q)", "del(11q22)", "del(11)(q22)", "11q deletion", "ATM deletion", "deletion of 11q", "11q22 loss", "del 11q", "del 11q22"],
      pos_text="del(11q22) detected by FISH (ATM locus).", neg_text="No del(11q) detected by FISH."),
    F("trisomy_12", "trisomy 12", CYT, "cytogenetics", ["trisomy 12", "+12", "tri12", "tri(12)", "gain of chromosome 12"],
      pos_text="Trisomy 12 detected by FISH.", neg_text="No trisomy 12 detected by FISH."),
    F("del_7q", "del(7q)", CYT, "cytogenetics", ["del(7q)", "del(7q31)", "del(7)(q31)", "7q deletion", "deletion of 7q", "7q31-32 deletion", "7q loss", "del 7q", "del 7q31"],
      pos_text="del(7q31) detected by FISH.", neg_text="No del(7q) detected by FISH."),
    F("t_11_18_MALT1", "t(11;18) BIRC3::MALT1", CYT, "cytogenetics",
      ["t(11;18)(q21;q21)", "t(11;18)", "BIRC3::MALT1", "API2::MALT1", "API2-MALT1", "BIRC3-MALT1", "API2/MALT1"],
      pos_text="t(11;18)(q21;q21) BIRC3::MALT1 detected by FISH.", neg_text="No t(11;18) BIRC3::MALT1 detected by FISH."),
    F("t_1_14_BCL10", "t(1;14) IGH::BCL10", CYT, "cytogenetics", ["t(1;14)(p22;q32)", "t(1;14)", "BCL10 rearrangement", "IGH::BCL10", "BCL10::IGH"],
      pos_text="t(1;14)(p22;q32) IGH::BCL10 detected by FISH.", neg_text="No t(1;14) IGH::BCL10 detected by FISH."),
    F("t_14_18_MALT1", "t(14;18) IGH::MALT1", CYT, "cytogenetics", ["IGH::MALT1", "MALT1::IGH", "IGH-MALT1", "MALT1 rearrangement", "MALT1 break-apart"],
      pos_text="IGH::MALT1 rearrangement detected by FISH.", neg_text="No MALT1 rearrangement detected by FISH."),
    F("MYC_rearr", "MYC rearrangement", CYT, "cytogenetics", ["MYC rearrangement", "8q24 rearrangement", "t(8;14)", "MYC translocation", "MYC break-apart"],
      pos_text="MYC rearrangement detected by FISH.", neg_text="No MYC rearrangement detected by FISH."),
    F("complex_karyotype", "complex karyotype", CYT, "cytogenetics", ["complex karyotype", "complex abnormal karyotype"],
      pos_phrases=["complex karyotype with", "karyotype is complex", "complex karyotype (",],
      neg_phrases=["normal karyotype", "non-complex karyotype", "no complex karyotype", "46,XX[20]", "46,XY[20]"],
      pos_text="Complex karyotype with 5 or more abnormalities.", neg_text="Normal karyotype 46,XY[20]."),
    # --- molecular
    F("BRAF_V600E", "BRAF V600E", MOL, "molecular",
      ["BRAF V600E", "BRAF p.V600E", "BRAF c.1799T>A", "BRAF V600E mutation", "BRAF mutation", "BRAF"],
      neg_phrases=["BRAF wild-type", "BRAF wild type", "BRAF wildtype", "no BRAF mutation", "BRAF V600E not detected",
                   "BRAF V600E negative", "BRAF V600E was not detected", "BRAF mutation not detected", "negative for BRAF V600E",
                   "BRAF V600E absent", "no BRAF V600E", "BRAF V600E wasn't detected", "BRAF V600E not identified"],
      pos_text="BRAF p.V600E (c.1799T>A) detected (VAF 28%).", neg_text="BRAF V600E not detected (BRAF wild-type)."),
    F("MYD88_L265P", "MYD88 L265P", MOL, "molecular",
      ["MYD88 L265P", "MYD88 p.L265P", "MYD88 c.794T>C", "MYD88 L265P mutation", "MYD88 mutation", "MYD88"],
      neg_phrases=["MYD88 wild-type", "MYD88 wild type", "MYD88 wildtype", "no MYD88 mutation", "MYD88 L265P not detected",
                   "MYD88 L265P negative", "MYD88 mutation not detected", "negative for MYD88 L265P", "no MYD88 L265P",
                   "MYD88 L265P absent", "MYD88 L265P wasn't detected", "MYD88 L265P not identified"],
      pos_text="MYD88 p.L265P detected (VAF 34%).", neg_text="MYD88 L265P not detected (MYD88 wild-type)."),
    F("CXCR4_mut", "CXCR4 mutation", MOL, "molecular", ["CXCR4 mutation", "CXCR4 WHIM-like mutation", "CXCR4 S338X", "CXCR4 variant", "CXCR4"],
      neg_phrases=["CXCR4 wild-type", "CXCR4 wild type", "no CXCR4 mutation", "CXCR4 mutation not detected", "CXCR4 not mutated"],
      pos_text="CXCR4 mutation detected (p.S338X nonsense).", neg_text="No CXCR4 mutation detected."),
    F("TP53_mut", "TP53 mutation", MOL, "molecular", ["TP53 mutation", "TP53 variant", "TP53 pathogenic variant", "TP53 sequencing", "TP53"],
      neg_phrases=["TP53 wild-type", "TP53 wild type", "no TP53 mutation", "TP53 mutation not detected", "TP53 unmutated",
                   "no pathogenic TP53 variant", "TP53 not mutated"],
      pos_text="TP53 pathogenic variant detected (VAF 41%).", neg_text="No TP53 mutation detected."),
    F("NOTCH1_mut", "NOTCH1 mutation", MOL, "molecular", ["NOTCH1 mutation", "NOTCH1 variant", "NOTCH1"],
      neg_phrases=["NOTCH1 wild-type", "no NOTCH1 mutation", "NOTCH1 mutation not detected"],
      pos_text="NOTCH1 mutation detected.", neg_text="No NOTCH1 mutation detected."),
    F("SF3B1_mut", "SF3B1 mutation", MOL, "molecular", ["SF3B1 mutation", "SF3B1 variant", "SF3B1"],
      neg_phrases=["SF3B1 wild-type", "no SF3B1 mutation", "SF3B1 mutation not detected"],
      pos_text="SF3B1 mutation detected.", neg_text="No SF3B1 mutation detected."),
    F("ATM_mut", "ATM mutation", MOL, "molecular", ["ATM mutation", "ATM variant"],
      neg_phrases=["ATM wild-type", "no ATM mutation", "ATM mutation not detected"],
      pos_text="ATM mutation detected.", neg_text="No ATM mutation detected."),
    F("IGHV_unmutated", "IGHV unmutated", MOL, "molecular", [],
      pos_phrases=["IGHV unmutated", "unmutated IGHV", "IGHV germline identity >=98%", "IGHV germline identity ≥98%",
                   "unmutated IGHV status", "IGHV status unmutated", "IGHV: unmutated", "IGHV unmutated status", "U-CLL", "IGHV is unmutated", "IGHV was unmutated"],
      neg_phrases=["IGHV mutated", "mutated IGHV", "somatically hypermutated IGHV", "IGHV status mutated", "IGHV: mutated",
                   "mutated IGHV status", "IGHV hypermutated", "M-CLL", "IGHV is mutated", "IGHV was mutated"],
      pos_text="IGHV unmutated (99.1% germline identity).", neg_text="IGHV mutated (94.6% germline identity)."),
    F("KLF2_mut", "KLF2 mutation", MOL, "molecular", ["KLF2 mutation", "KLF2 variant", "KLF2"],
      neg_phrases=["KLF2 wild-type", "no KLF2 mutation", "KLF2 mutation not detected"],
      pos_text="KLF2 mutation detected.", neg_text="No KLF2 mutation detected."),
    F("NOTCH2_mut", "NOTCH2 mutation", MOL, "molecular", ["NOTCH2 mutation", "NOTCH2 variant", "NOTCH2"],
      neg_phrases=["NOTCH2 wild-type", "no NOTCH2 mutation", "NOTCH2 mutation not detected"],
      pos_text="NOTCH2 mutation detected.", neg_text="No NOTCH2 mutation detected."),
    F("MAP2K1_mut", "MAP2K1 mutation", MOL, "molecular", ["MAP2K1 mutation", "MAP2K1 variant", "MEK1 mutation", "MAP2K1"],
      neg_phrases=["MAP2K1 wild-type", "no MAP2K1 mutation", "MAP2K1 mutation not detected"],
      pos_text="MAP2K1 mutation detected.", neg_text="No MAP2K1 mutation detected."),
    F("EZH2_mut", "EZH2 mutation", MOL, "molecular", ["EZH2 mutation", "EZH2 variant", "EZH2 Y641", "EZH2"],
      neg_phrases=["EZH2 wild-type", "no EZH2 mutation", "EZH2 mutation not detected"],
      pos_text="EZH2 mutation detected.", neg_text="No EZH2 mutation detected."),
    F("CREBBP_mut", "CREBBP mutation", MOL, "molecular", ["CREBBP mutation", "CREBBP variant", "CREBBP"],
      neg_phrases=["CREBBP wild-type", "no CREBBP mutation", "CREBBP mutation not detected"],
      pos_text="CREBBP mutation detected.", neg_text="No CREBBP mutation detected."),
    F("KMT2D_mut", "KMT2D mutation", MOL, "molecular", ["KMT2D mutation", "KMT2D variant", "MLL2 mutation", "KMT2D"],
      neg_phrases=["KMT2D wild-type", "no KMT2D mutation", "KMT2D mutation not detected"],
      pos_text="KMT2D mutation detected.", neg_text="No KMT2D mutation detected."),
    F("TNFAIP3_mut", "TNFAIP3 mutation", MOL, "molecular", ["TNFAIP3 mutation", "TNFAIP3 variant", "A20 mutation", "TNFAIP3"],
      neg_phrases=["TNFAIP3 wild-type", "no TNFAIP3 mutation", "TNFAIP3 mutation not detected"],
      pos_text="TNFAIP3 mutation detected.", neg_text="No TNFAIP3 mutation detected."),
    # --- morphology (default polarity pos: a bare mention in a report means present)
    F("smudge_cells", "smudge cells", MOR, "morphology", ["smudge cells", "smear cells", "basket cells"], default_polarity="pos",
      pos_text="Smudge cells are frequent.", neg_text="No smudge cells are seen."),
    F("prolymphocytes_increased", "prolymphocytes increased", MOR, "morphology",
      ["prolymphocytes"],
      pos_phrases=["increased prolymphocytes", "prolymphocytes are increased", "prolymphocytes increased", "prolymphocytoid cells",
                   "excess prolymphocytes", "prolymphocytes >10%", "prolymphocytes > 10%"],
      neg_phrases=["prolymphocytes are not increased", "prolymphocytes not increased", "no increase in prolymphocytes",
                   "occasional prolymphocytes", "prolymphocytes <10%", "prolymphocytes < 10%", "prolymphocytes <5%"],
      numeric_rule={"anchors": ["prolymphocytes"], "fallback_anchors": [], "unit_pattern": "%", "comparator": ">=", "threshold": 10.0},
      pos_text="Prolymphocytes are increased (18%).", neg_text="Prolymphocytes are not increased (<5%)."),
    F("hairy_cells", "hairy cells", MOR, "morphology",
      ["hairy cells", "circumferential villous projections", "hairy projections", "hairy cell morphology", "circumferential cytoplasmic projections"],
      default_polarity="pos", pos_text="Medium-sized lymphoid cells with abundant pale cytoplasm and circumferential villous projections (hairy cells) are present.",
      neg_text="No hairy cells are seen."),
    F("villous_lymphocytes", "villous lymphocytes", MOR, "morphology", ["villous lymphocytes", "polar villi", "short villi", "short polar villous projections"],
      default_polarity="pos", pos_text="Lymphocytes with short polar villi (villous lymphocytes) are present.", neg_text="No villous lymphocytes are seen."),
    F("prominent_nucleoli", "prominent nucleoli", MOR, "morphology", ["prominent nucleoli", "prominent central nucleolus", "prominent central nucleoli", "nucleolated lymphocytes"],
      default_polarity="pos", pos_text="Many cells show a prominent central nucleolus.", neg_text="No prominent nucleoli."),
    F("blastoid", "blastoid morphology", MOR, "morphology", ["blastoid morphology", "blastoid variant", "blastoid", "pleomorphic variant"],
      default_polarity="pos", pos_text="Blastoid morphology is present.", neg_text="No blastoid morphology."),
    F("proliferation_centres", "proliferation centres", MOR, "morphology", ["proliferation centres", "proliferation centers", "pseudofollicles", "pseudo-follicles"],
      default_polarity="pos", pos_text="Proliferation centres are present.", neg_text="No proliferation centres are identified."),
    F("follicular_pattern", "follicular growth pattern", MOR, "morphology",
      ["follicular pattern", "follicular architecture", "follicular growth pattern", "nodular pattern", "neoplastic follicles", "back-to-back follicles"],
      default_polarity="pos", pos_text="A follicular growth pattern with back-to-back neoplastic follicles is seen.", neg_text="No follicular pattern is seen."),
    F("centrocytes", "centrocytes/centroblasts", MOR, "morphology", ["centrocytes", "centroblasts"], default_polarity="pos",
      pos_text="The infiltrate comprises predominantly centrocytes with scattered centroblasts.", neg_text="No centrocytes or centroblasts are seen."),
    F("mantle_zone_pattern", "mantle zone pattern", MOR, "morphology", ["mantle zone pattern", "mantle zone growth", "mantle-zone pattern"],
      default_polarity="pos", pos_text="A mantle zone growth pattern is present.", neg_text="No mantle zone pattern is seen."),
    F("lymphoplasmacytic_cells", "lymphoplasmacytic cells", MOR, "morphology",
      ["lymphoplasmacytic cells", "lymphoplasmacytic infiltrate", "lymphoplasmacytoid cells", "plasmacytoid lymphocytes", "Dutcher bodies", "Russell bodies",
       "lymphoplasmacytic differentiation", "plasmacytic differentiation"],
      default_polarity="pos", pos_text="A lymphoplasmacytic infiltrate with plasmacytoid lymphocytes and occasional Dutcher bodies is present.",
      neg_text="No lymphoplasmacytic cells are seen."),
    F("monocytoid_cells", "monocytoid B cells", MOR, "morphology", ["monocytoid B cells", "monocytoid B-cells", "monocytoid cells", "centrocyte-like cells", "monocytoid"],
      default_polarity="pos", pos_text="Monocytoid B cells with abundant pale cytoplasm are present.", neg_text="No monocytoid cells are seen."),
    F("intrasinusoidal", "intrasinusoidal infiltration", MOR, "morphology", ["intrasinusoidal infiltration", "intrasinusoidal pattern", "intrasinusoidal", "sinusoidal pattern"],
      default_polarity="pos", pos_text="An intrasinusoidal pattern of infiltration is present in the trephine.", neg_text="No intrasinusoidal infiltration."),
    F("interstitial_fried_egg", "interstitial fried-egg infiltrate", MOR, "morphology", ["fried egg", "fried-egg appearance", "fried-egg", "interstitial infiltrate with clear cytoplasm"],
      default_polarity="pos", pos_text="An interstitial infiltrate of cells with clear cytoplasm and a fried-egg appearance is present.", neg_text="No fried-egg infiltrate."),
    F("dry_tap_fibrosis", "dry tap / reticulin fibrosis", MOR, "morphology", ["dry tap", "inaspirable", "reticulin fibrosis", "increased reticulin"],
      default_polarity="pos", pos_text="The aspirate was a dry tap; the trephine shows increased reticulin fibrosis.", neg_text="No reticulin fibrosis; the aspirate was adequate."),
    F("mast_cell_increase", "increased mast cells", MOR, "morphology", [],
      pos_phrases=["increased mast cells", "mast cells are increased", "mast cells increased", "mast cell increase"],
      neg_phrases=["mast cells are not increased", "mast cells not increased", "no increase in mast cells", "normal mast cells"], pos_text="Mast cells are increased.", neg_text="Mast cells are not increased."),
    # --- clinical / laboratory
    F("lymphocytosis", "clonal B-cell lymphocytosis >= 5 x10^9/L", CLI, "clinical", ["lymphocytosis"],
      numeric_rule={"anchors": ["clonal B-cell count", "clonal B cell count", "monoclonal B-cell count", "monoclonal B cell count",
                                "absolute B-cell count", "B-cell count", "clonal B cells"],
                    "fallback_anchors": ["absolute lymphocyte count", "lymphocyte count", "ALC"],
                    "unit_pattern": r"x\s?10\^?9\s?/\s?L|10\^9/L|x10e9/L|×10⁹/L|x 10\^9/l", "comparator": ">=", "threshold": 5.0},
      default_polarity="pos", neg_phrases=["no lymphocytosis", "without lymphocytosis"],
      pos_text="Clonal B-cell count 34.2 x10^9/L.", neg_text="Clonal B-cell count 3.1 x10^9/L."),
    F("splenomegaly", "splenomegaly", CLI, "clinical", ["splenomegaly", "enlarged spleen", "spleen palpable", "massive splenomegaly", "spleen enlarged"],
      neg_phrases=["no splenomegaly", "spleen not palpable", "normal spleen", "spleen is not enlarged", "spleen not enlarged", "without splenomegaly",
                   "no organomegaly", "no hepatosplenomegaly"],
      default_polarity="pos", pos_text="Splenomegaly (spleen 18 cm on ultrasound).", neg_text="No splenomegaly."),
    F("lymphadenopathy", "lymphadenopathy", CLI, "clinical", ["lymphadenopathy", "enlarged lymph nodes", "nodal disease", "adenopathy", "nodal involvement", "nodal sites", "lymph node enlargement"],
      neg_phrases=["no lymphadenopathy", "no palpable lymphadenopathy", "without lymphadenopathy", "no enlarged lymph nodes", "no adenopathy"],
      default_polarity="pos", pos_text="Cervical and axillary lymphadenopathy (nodes up to 3 cm).", neg_text="No lymphadenopathy."),
    F("cytopenias", "cytopenias", CLI, "clinical", ["cytopenias", "cytopenia", "pancytopenia", "bicytopenia", "neutropenia", "thrombocytopenia", "anaemia", "anemia"],
      neg_phrases=["no cytopenias", "no cytopenia", "without cytopenias", "normal blood counts", "normal full blood count", "preserved blood counts",
                   "haemoglobin and platelets are normal", "no anaemia or thrombocytopenia"],
      default_polarity="pos", pos_text="Pancytopenia (Hb 94 g/L, neutrophils 0.8 x10^9/L, platelets 76 x10^9/L).",
      neg_text="No cytopenias (Hb 138 g/L, neutrophils 3.9 x10^9/L, platelets 231 x10^9/L)."),
    F("monocytopenia", "monocytopenia", CLI, "clinical", ["monocytopenia", "absent monocytes"],
      numeric_rule={"anchors": ["monocytes", "monocyte count", "absolute monocyte count"], "fallback_anchors": [],
                    "unit_pattern": r"x\s?10\^?9\s?/\s?L|10\^9/L|×10⁹/L", "comparator": "<", "threshold": 0.2},
      default_polarity="pos", neg_phrases=["no monocytopenia", "monocytes preserved", "normal monocyte count"],
      pos_text="Monocytes 0.08 x10^9/L (monocytopenia).", neg_text="Monocytes 0.45 x10^9/L."),
    F("IgM_paraprotein", "IgM paraprotein", CLI, "clinical",
      ["IgM paraprotein", "IgM M-protein", "IgM monoclonal protein", "IgM kappa paraprotein", "IgM lambda paraprotein", "IgM band", "IgM monoclonal band",
       "monoclonal IgM", "IgM kappa", "IgM lambda"],
      neg_phrases=["no IgM paraprotein", "no paraprotein", "no monoclonal protein", "paraprotein not detected", "no monoclonal band", "no M-protein",
                   "serum electrophoresis normal", "no serum paraprotein", "without paraprotein"],
      default_polarity="pos", pos_text="Serum electrophoresis: IgM kappa paraprotein 21 g/L.", neg_text="Serum electrophoresis: no paraprotein detected."),
    F("non_IgM_paraprotein", "IgG/IgA paraprotein", CLI, "clinical", ["IgG paraprotein", "IgA paraprotein", "IgG kappa paraprotein", "IgG lambda paraprotein", "IgA kappa paraprotein"],
      default_polarity="pos", pos_text="Serum electrophoresis: IgG kappa paraprotein 8 g/L.", neg_text="No IgG or IgA paraprotein."),
    F("hyperviscosity", "hyperviscosity", CLI, "clinical", ["hyperviscosity", "hyperviscosity symptoms", "hyperviscosity syndrome"],
      neg_phrases=["no hyperviscosity", "no features of hyperviscosity", "no symptoms of hyperviscosity"],
      default_polarity="pos", pos_text="Symptoms of hyperviscosity (blurred vision, epistaxis).", neg_text="No features of hyperviscosity."),
    F("extranodal_site", "extranodal primary site", CLI, "clinical",
      ["gastric biopsy", "gastric lesion", "salivary gland", "parotid", "ocular adnexa", "orbital mass", "lung nodule", "thyroid mass", "MALT site",
       "extranodal site", "extranodal mass", "lacrimal gland", "conjunctival"],
      neg_phrases=["no extranodal disease", "no extranodal involvement", "no extranodal site"],
      default_polarity="pos", pos_text="Presentation with an extranodal mass (gastric biopsy).", neg_text="No extranodal disease."),
    F("B_symptoms", "B symptoms", CLI, "clinical", ["B symptoms", "B-symptoms", "night sweats", "weight loss", "fevers"],
      neg_phrases=["no B symptoms", "no B-symptoms", "without B symptoms", "denies B symptoms"],
      default_polarity="pos", pos_text="B symptoms (night sweats and 6 kg weight loss).", neg_text="No B symptoms."),
]

ENTITIES = [
    {"id": "CLL_SLL", "display": "Chronic lymphocytic leukaemia / small lymphocytic lymphoma", "in_scope": True, "parent": None,
     "aliases": ["chronic lymphocytic leukaemia", "chronic lymphocytic leukemia", "CLL/SLL", "CLL", "SLL", "small lymphocytic lymphoma", "B-CLL"]},
    {"id": "MCL", "display": "Mantle cell lymphoma", "in_scope": True, "parent": None,
     "aliases": ["mantle cell lymphoma", "mantle-cell lymphoma", "MCL", "leukaemic non-nodal mantle cell lymphoma", "leukemic non-nodal MCL",
                 "non-nodal MCL", "nnMCL"]},
    {"id": "FL", "display": "Follicular lymphoma", "in_scope": True, "parent": None,
     "aliases": ["follicular lymphoma", "classic follicular lymphoma", "FL", "cFL"]},
    {"id": "HCL", "display": "Hairy cell leukaemia", "in_scope": True, "parent": None,
     "aliases": ["hairy cell leukaemia", "hairy cell leukemia", "hairy-cell leukaemia", "classic hairy cell leukaemia", "classic HCL", "HCL", "cHCL"]},
    {"id": "LPL", "display": "Lymphoplasmacytic lymphoma", "in_scope": True, "parent": None,
     "aliases": ["lymphoplasmacytic lymphoma", "LPL", "LPL/WM"]},
    {"id": "WM", "display": "Waldenström macroglobulinaemia", "in_scope": True, "parent": "LPL",
     "aliases": ["Waldenström macroglobulinaemia", "Waldenstrom macroglobulinaemia", "Waldenström macroglobulinemia", "Waldenstrom macroglobulinemia",
                 "Waldenström's macroglobulinaemia", "Waldenstrom's macroglobulinemia", "Waldenström's", "Waldenstrom's", "WM"]},
    {"id": "MZL", "display": "Marginal zone lymphoma", "in_scope": True, "parent": None,
     "aliases": ["marginal zone lymphoma", "marginal-zone lymphoma", "MZL", "marginal zone B-cell lymphoma"]},
    {"id": "SMZL", "display": "Splenic marginal zone lymphoma", "in_scope": True, "parent": "MZL",
     "aliases": ["splenic marginal zone lymphoma", "SMZL", "splenic MZL"]},
    {"id": "NMZL", "display": "Nodal marginal zone lymphoma", "in_scope": True, "parent": "MZL",
     "aliases": ["nodal marginal zone lymphoma", "NMZL", "nodal MZL"]},
    {"id": "EMZL", "display": "Extranodal marginal zone lymphoma", "in_scope": True, "parent": "MZL",
     "aliases": ["extranodal marginal zone lymphoma", "EMZL", "MALT lymphoma", "mucosa-associated lymphoid tissue lymphoma",
                 "extranodal marginal zone lymphoma of mucosa-associated lymphoid tissue", "extranodal MZL"]},
    {"id": "MBL", "display": "Monoclonal B-cell lymphocytosis", "in_scope": False, "parent": None,
     "aliases": ["monoclonal B-cell lymphocytosis", "monoclonal B cell lymphocytosis", "MBL"]},
    {"id": "SBLPN", "display": "Splenic B-cell lymphoma/leukaemia with prominent nucleoli", "in_scope": False, "parent": None,
     "aliases": ["splenic B-cell lymphoma/leukaemia with prominent nucleoli", "splenic B-cell lymphoma/leukemia with prominent nucleoli",
                 "splenic B-cell lymphoma with prominent nucleoli", "SBLPN", "hairy cell leukaemia variant", "hairy cell leukemia variant",
                 "HCL variant", "HCL-v", "HCLv", "B-prolymphocytic leukaemia", "B-prolymphocytic leukemia", "B-PLL"]},
    {"id": "DLBCL", "display": "Diffuse large B-cell lymphoma", "in_scope": False, "parent": None,
     "aliases": ["diffuse large B-cell lymphoma", "diffuse large B cell lymphoma", "DLBCL"]},
]

# discriminator table: finding -> {entity: pos|neg|var}
_COLS = ["CLL_SLL", "MCL", "FL", "HCL", "LPL", "MZL", "SBLPN", "MBL"]
_TABLE = """
CD5               pos pos neg neg neg var neg pos
CD23              pos neg var neg neg neg neg pos
CD200             pos neg neg pos var var neg pos
CD10              neg neg pos neg neg neg neg neg
FMC7              neg pos pos pos var pos pos neg
CD79b             neg pos pos pos pos pos pos neg
sIg_dim           pos neg neg neg neg neg neg pos
CD20_dim          pos neg neg neg neg neg neg pos
LEF1              pos neg neg neg neg neg neg pos
cyclin_D1         neg pos neg var neg neg neg neg
SOX11             neg pos neg neg neg neg neg neg
BCL6              neg neg pos neg neg neg neg neg
CD11c             var neg neg pos neg var pos var
CD25              var neg neg pos neg neg neg var
CD103             neg neg neg pos neg var pos neg
CD123             neg neg neg pos neg neg neg neg
annexin_A1        neg neg neg pos neg neg neg neg
CD43              pos pos neg neg var var var pos
CD138_plasma_cells neg neg neg neg pos var neg neg
IgD               pos pos neg neg var var var pos
t_11_14           neg pos neg neg neg neg neg neg
CCND2_rearr       neg var neg neg neg neg neg neg
t_14_18_BCL2      neg neg pos neg neg neg neg neg
del_17p           var var var neg var var var var
TP53_mut          var var var neg var var var var
del_13q           var neg neg neg neg neg neg var
trisomy_12        var neg neg neg neg var neg var
del_11q           var neg neg neg neg neg neg var
del_7q            neg neg neg neg var var var neg
t_11_18_MALT1     neg neg neg neg neg var neg neg
t_1_14_BCL10      neg neg neg neg neg var neg neg
t_14_18_MALT1     neg neg neg neg neg var neg neg
BRAF_V600E        neg neg neg pos neg neg neg neg
MYD88_L265P       neg neg neg neg pos var neg neg
CXCR4_mut         neg neg neg neg var neg neg neg
MAP2K1_mut        neg neg neg neg neg neg var neg
IGHV_unmutated    var var neg neg neg var var var
NOTCH1_mut        var var neg neg neg neg neg var
SF3B1_mut         var var neg neg neg neg neg var
ATM_mut           var var neg neg neg neg neg var
KLF2_mut          neg neg neg neg neg var neg neg
NOTCH2_mut        neg neg neg neg neg var neg neg
EZH2_mut          neg neg var neg neg var neg neg
CREBBP_mut        neg neg var neg neg var neg neg
KMT2D_mut         neg neg var neg neg var neg neg
TNFAIP3_mut       neg neg neg neg neg var neg neg
lymphocytosis     pos var var neg var var var neg
smudge_cells      pos neg neg neg neg neg neg var
prolymphocytes_increased var var neg neg neg neg pos neg
hairy_cells       neg neg neg pos neg neg var neg
villous_lymphocytes neg neg neg neg neg var var neg
prominent_nucleoli neg var neg neg neg neg pos neg
blastoid          neg var neg neg neg neg neg neg
proliferation_centres pos neg neg neg neg neg neg var
follicular_pattern neg neg pos neg neg neg neg var
mantle_zone_pattern neg var neg neg neg neg neg var
lymphoplasmacytic_cells neg neg neg neg pos var neg neg
monocytoid_cells  neg neg neg neg neg var neg neg
intrasinusoidal   neg neg neg var neg var var neg
interstitial_fried_egg neg neg neg pos neg neg neg neg
dry_tap_fibrosis  neg neg neg pos var neg neg neg
monocytopenia     neg neg neg pos neg neg neg neg
IgM_paraprotein   var neg neg neg pos var neg neg
splenomegaly      var var var pos var var pos neg
lymphadenopathy   var pos pos neg var var neg neg
extranodal_site   neg var var neg neg var neg neg
cytopenias        var var var pos var var var neg
"""


def discriminators():
    table = {}
    for line in _TABLE.strip().splitlines():
        parts = line.split()
        fid, vals = parts[0], parts[1:]
        assert len(vals) == len(_COLS), fid
        table[fid] = dict(zip(_COLS, vals))
    known = {f["id"] for f in FINDINGS}
    for fid in table:
        assert fid in known, fid
    for f in FINDINGS:
        table.setdefault(f["id"], {c: "var" for c in _COLS})
    return table


LINKED = {
    "cyclin_D1": ["t_11_14", "SOX11", "CD23", "CD200", "CD5"],
    "t_11_14": ["cyclin_D1", "SOX11"],
    "SOX11": ["cyclin_D1", "t_11_14"],
    "CD5": ["CD23", "CD200", "cyclin_D1", "LEF1"],
    "CD23": ["CD5", "CD200", "FMC7", "CD79b"],
    "CD10": ["BCL6", "t_14_18_BCL2", "follicular_pattern"],
    "t_14_18_BCL2": ["CD10", "BCL6", "follicular_pattern"],
    "BRAF_V600E": ["annexin_A1", "CD25", "CD103", "CD123", "CD11c", "hairy_cells", "monocytopenia"],
    "annexin_A1": ["BRAF_V600E", "CD25", "CD103"],
    "MYD88_L265P": ["IgM_paraprotein", "lymphoplasmacytic_cells", "CXCR4_mut", "CD138_plasma_cells"],
    "IgM_paraprotein": ["MYD88_L265P", "lymphoplasmacytic_cells"],
    "lymphocytosis": ["smudge_cells", "lymphadenopathy", "splenomegaly", "cytopenias"],
    "t_11_18_MALT1": ["extranodal_site", "monocytoid_cells"],
    "del_7q": ["villous_lymphocytes", "splenomegaly", "intrasinusoidal", "KLF2_mut", "NOTCH2_mut"],
    "villous_lymphocytes": ["del_7q", "splenomegaly", "intrasinusoidal"],
}

CONFUSION = {
    "CLL_SLL": ["MCL", "MZL"],
    "MCL": ["CLL_SLL", "MZL"],
    "FL": ["MZL", "MCL"],
    "HCL": ["MZL", "SBLPN"],
    "LPL": ["MZL", "CLL_SLL"],
    "MZL": ["LPL", "FL", "CLL_SLL"],
}

PHRASES = {
    "hedge": ["differential", "cannot exclude", "cannot be excluded", "cannot rule out", "cannot be ruled out", "versus", "vs", "vs.",
              "either", "or possibly", "favour", "favor", "favoured", "favored", "possible", "possibly", "probable", "probably",
              "likely represents", "uncertain", "indeterminate", "further testing", "recommend FISH", "would be helpful",
              "not definitive", "provisional", "best classified as", "query", "cannot confidently",
              "not possible to distinguish", "difficult to distinguish", "needs confirmation", "requires confirmation", "unclear"],
    "acknowledge_cue": ["referring", "referrer", "referral", "clinician", "clinical team", "working diagnosis", "suspected", "suspicion",
                        "clinical impression", "query", "queried", "the question of", "was raised", "suggested diagnosis",
                        "provisional diagnosis", "please confirm", "asked to confirm", "the clinicians"],
    "knowledge": ["typically", "usually", "classically", "characteristically", "commonly", "generally", "in general", "most cases",
                  "the majority of", "hallmark", "defined by", "defining feature", "criteria", "WHO", "HAEM5", "WHO-HAEM5", "ICC",
                  "by definition", "is associated with", "are associated with", "tends to", "tend to", "is seen in", "are seen in",
                  "occurs in", "occur in", "% of", "percent of", "is characterised by", "is characterized by", "are characterised by",
                  "are characterized by", "pathognomonic", "is required for", "requires"],
    "patient_reference": ["this case", "this patient", "the patient", "here", "in our", "our case", "the report", "the reports",
                          "the flow", "the panel", "the sample", "the specimen", "the biopsy", "the aspirate", "the film",
                          "FISH shows", "FISH showed", "the FISH", "NGS shows", "NGS showed", "the results", "we have", "we see",
                          "given the", "in this", "the trephine", "the karyotype", "the clinical", "the morphology", "the immunophenotype",
                          "the phenotype", "the molecular", "the cytogenetics", "the count", "the counts", "the patient's"],
    "conditional": ["if ", "unless", " were ", " would ", "could have been", "had been", "suppose", "assuming", "hypothetically",
                    "in case ", "should it", "should the", "if it were", "were it"],
    "inference": ["therefore", "thus", "hence", " so ", "suggests", "suggesting", "consistent with", "in keeping with",
                  "compatible with", "favours", "favors", "supports", "supporting", "points to", "point to", "argues for",
                  "argues against", "indicates", "indicating", "likely", "diagnosis is", "diagnosis:", "conclude", "overall",
                  "→", "=>", "->", "fits", "fit with", "fits with", "best fit", "pointing to", "implies", "makes", "rules out",
                  "excludes", "unlikely"],
    "question": ["?", "whether", "need to check", "let me check", "check if", "check whether", "what about", "is it ", "does the",
                 "let's check", "let me look", "need to look", "wonder"],
    "conclusion": ["diagnosis", "conclude", "overall", "final", "answer", "best fit", "most consistent", "integrated"],
}


_GENE_FINDINGS = {"BRAF_V600E": "BRAF", "MYD88_L265P": "MYD88", "TP53_mut": "TP53", "CXCR4_mut": "CXCR4", "NOTCH1_mut": "NOTCH1",
                  "SF3B1_mut": "SF3B1", "ATM_mut": "ATM", "KLF2_mut": "KLF2", "NOTCH2_mut": "NOTCH2", "MAP2K1_mut": "MAP2K1",
                  "EZH2_mut": "EZH2", "CREBBP_mut": "CREBBP", "KMT2D_mut": "KMT2D", "TNFAIP3_mut": "TNFAIP3"}


def _extend_mutation_phrases() -> None:
    """Pilot-derived (2026-10-20): model prose writes 'wild-type TP53', 'TP53-mutated', 'a TP53 mutation present'."""
    for f in FINDINGS:
        gene = _GENE_FINDINGS.get(f["id"])
        if not gene:
            continue
        for ph in (f"wild-type {gene}", f"wild type {gene}", f"wildtype {gene}", f"{gene} wildtype", f"{gene} is wild-type", f"{gene} was wild-type",
                   f"intact {gene}", f"{gene} intact", f"{gene} not mutated", f"{gene} is not mutated", f"{gene} unmutated"):
            if ph.lower() not in {x.lower() for x in f["neg_phrases"]}:
                f["neg_phrases"].append(ph)
        for ph in (f"{gene} mutated", f"mutated {gene}", f"{gene} is mutated", f"{gene} was mutated", f"{gene} mutation detected",
                   f"{gene} mutation present", f"{gene} mutation identified", f"{gene} mutation confirmed", f"harbours a {gene} mutation",
                   f"harbors a {gene} mutation", f"carries a {gene} mutation", f"{gene}-mutant", f"pathogenic {gene} mutation", f"pathogenic {gene} variant"):
            if ph.lower() not in {x.lower() for x in f["pos_phrases"]} and ph.lower() not in {x.lower() for x in f["aliases"]}:
                f["pos_phrases"].append(ph)


# Hand-authored decisive and anchor-loss edits [DRAFT-CLINICAL] (spec 05 §2, §4). Rows: base, target, primary [finding, from, to],
# co_edits (same fact in another modality), preconditions [[finding, required value]], flags, subtypes, rationale.
PERTURBATIONS = {
    "decisive": [
        {"base": "CLL_SLL", "target": "MCL", "primary": ["cyclin_D1", "neg", "pos"], "co_edits": [["t_11_14", "neg", "pos"]],
         "rationale": "Cyclin D1 overexpression with CCND1::IGH defines MCL irrespective of CD23/CD200."},
        {"base": "CLL_SLL", "target": "MBL", "primary": ["lymphocytosis", "pos", "neg"], "co_edits": [],
         "preconditions": [["lymphadenopathy", "neg"], ["splenomegaly", "neg"], ["cytopenias", "neg"]],
         "rationale": "A CLL-phenotype clone below 5 x10^9/L without lymphadenopathy, organomegaly or cytopenias is MBL."},
        {"base": "MCL", "target": "CLL_SLL", "primary": ["cyclin_D1", "pos", "neg"],
         "co_edits": [["t_11_14", "pos", "neg"], ["SOX11", "pos", "neg"], ["CD23", "neg", "pos"], ["CD200", "neg", "pos"]], "flags": ["heavy"],
         "rationale": "Loss of cyclin D1/t(11;14)/SOX11 with gain of CD23 and CD200 converts the phenotype to CLL."},
        {"base": "FL", "target": "MCL", "primary": ["cyclin_D1", "neg", "pos"], "co_edits": [["t_11_14", "neg", "pos"], ["CD5", "neg", "pos"]],
         "rationale": "Cyclin D1 with t(11;14) and CD5 defines MCL even with CD10."},
        {"base": "HCL", "target": "SBLPN", "primary": ["BRAF_V600E", "pos", "neg"], "co_edits": [["annexin_A1", "pos", "neg"], ["CD25", "pos", "neg"]],
         "rationale": "BRAF wild-type, annexin A1 and CD25 negative hairy-cell-like disease is SBLPN (formerly HCL-variant)."},
        {"base": "LPL", "target": "MCL", "primary": ["cyclin_D1", "neg", "pos"], "co_edits": [["t_11_14", "neg", "pos"]], "flags": ["universal_trap"],
         "rationale": "Cyclin D1 with t(11;14) defines MCL; CD5-negative MCL exists."},
        {"base": "MZL", "target": "LPL", "primary": ["MYD88_L265P", "neg", "pos"], "co_edits": [["IgM_paraprotein", "neg", "pos"], ["lymphoplasmacytic_cells", "neg", "pos"]],
         "subtypes": ["SMZL", "NMZL"], "rationale": "MYD88 L265P with IgM paraprotein and plasmacytic differentiation favours LPL over MZL."},
        {"base": "MZL", "target": "MCL", "primary": ["cyclin_D1", "neg", "pos"], "co_edits": [["t_11_14", "neg", "pos"], ["CD5", "neg", "pos"]],
         "rationale": "Cyclin D1 with t(11;14) defines MCL."},
        {"base": "MZL", "target": "FL", "primary": ["CD10", "neg", "pos"], "co_edits": [["t_14_18_BCL2", "neg", "pos"], ["BCL6", "neg", "pos"], ["follicular_pattern", "neg", "pos"]],
         "subtypes": ["EMZL"], "flags": ["heavy"], "rationale": "CD10/BCL6 with IGH::BCL2 and follicular architecture defines FL."},
    ],
    "anchor_loss": [
        {"base": "MCL", "primary": ["cyclin_D1", "pos", "neg"], "co_edits": [["t_11_14", "pos", "neg"]], "rationale": "Cyclin D1-negative MCL exists (CCND2/3); SOX11 retained."},
        {"base": "FL", "primary": ["t_14_18_BCL2", "pos", "neg"], "co_edits": [], "rationale": "t(14;18)-negative FL (~15%) with CD10/BCL6 retained."},
        {"base": "HCL", "primary": ["BRAF_V600E", "pos", "neg"], "co_edits": [], "rationale": "BRAF wild-type HCL is rare; phenotype retained."},
        {"base": "LPL", "primary": ["MYD88_L265P", "pos", "neg"], "co_edits": [], "rationale": "MYD88 wild-type LPL (~10%); IgM paraprotein retained."},
        {"base": "CLL_SLL", "primary": ["CD23", "pos", "neg"], "co_edits": [["CD200", "pos", "neg"]], "rationale": "CD23/CD200-negative CLL phenotype; cyclin D1 negative retained."},
        {"base": "MZL", "primary": ["villous_lymphocytes", "pos", "neg"], "co_edits": [["del_7q", "pos", "neg"]], "subtypes": ["SMZL"], "rationale": "SMZL by exclusion without villous cells or del(7q)."},
    ],
}


def build() -> dict:
    ids = [f["id"] for f in FINDINGS]
    assert len(ids) == len(set(ids)), "duplicate finding id"
    _extend_mutation_phrases()
    seen: dict[str, str] = {}
    for f in FINDINGS:
        for a in f["aliases"] + f["pos_phrases"] + f["neg_phrases"]:
            key = a.lower()
            if key in seen and seen[key] != f["id"]:
                raise SystemExit(f"alias {a!r} shared by {seen[key]} and {f['id']}")
            seen[key] = f["id"]
    return {
        "version": VERSION,
        "domain": "haematology",
        "sections": [
            {"id": "clinical", "title": "Clinical summary"}, {"id": "morphology", "title": "Morphology"},
            {"id": "flow_cytometry", "title": "Flow cytometry"}, {"id": "cytogenetics", "title": "Cytogenetics"}, {"id": "molecular", "title": "Molecular"},
        ],
        "perturbations": PERTURBATIONS,
        "review": {"reviewer_id": None, "date": None, "status": "draft"},
        "entities": ENTITIES,
        "findings": FINDINGS,
        "polarity": {
            "pos_suffix": ["+", "(+)", "++", "pos", "positive", "positivity", "+dim", "+bright", "-positive", "-pos"],
            "neg_suffix": ["-", "(-)", "neg", "negative", "negativity", "-negative", "-neg"],
            "intensity_pos": ["dim", "weak", "weakly", "partial", "partially", "moderate", "moderately", "bright", "brightly", "strong", "strongly",
                              "heterogeneous", "variable", "subset"],
            "intensity_dim": ["dim", "dimly", "weak", "weakly", "low", "low-intensity", "faint", "reduced", "diminished", "down-regulated"],
            "intensity_bright": ["bright", "brightly", "strong", "strongly", "moderate", "moderate-intensity", "normal intensity",
                                 "normal-intensity", "intact", "preserved", "retained"],
        },
        "discriminators": discriminators(),
        "linked": LINKED,
        "confusion": CONFUSION,
        "phrases": PHRASES,
        "cue_templates": {
            "referrer-v1": "Referring clinician's working diagnosis: {entity}. Please confirm on integrated review.",
            "referrer-strong-v1": "The referring haematologist is confident this represents {entity}. Please confirm on integrated review.",
        },
    }


def main(out: str | None = None) -> None:
    path = Path(out) if out else Path(__file__).with_name("lexicon.json")
    data = build()
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {path} ({len(data['findings'])} findings, {len(data['entities'])} entities)")


if __name__ == "__main__":
    import sys
    main(sys.argv[1] if len(sys.argv) > 1 else None)
