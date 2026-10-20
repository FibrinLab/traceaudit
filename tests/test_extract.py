import pytest

from traceaudit import extract

TABLE = [
    ("CD5+, CD23+, CD200+, FMC7-, CD79b dim", {"CD5": "pos", "CD23": "pos", "CD200": "pos", "FMC7": "neg", "CD79b": "pos"}),
    ("positive for CD19, CD20 and CD10 but negative for CD5", {"CD19": "pos", "CD10": "pos", "CD5": "neg"}),
    ("no t(11;14) or t(14;18)", {"t_11_14": "neg", "t_14_18_BCL2": "neg"}),
    ("cyclin D1 and SOX11 expression is absent", {"cyclin_D1": "neg", "SOX11": "neg"}),
    ("Lacks CD103 and CD25; CD11c partial", {"CD103": "neg", "CD25": "neg", "CD11c": "pos"}),
    ("BRAF V600E detected (VAF 31%)", {"BRAF_V600E": "pos"}),
    ("BRAF wild-type", {"BRAF_V600E": "neg"}),
    ("IGHV unmutated (97.2% identity)", {"IGHV_unmutated": "pos"}),
    ("dim surface kappa", {"sIg_dim": "pos"}),
    ("moderate-intensity sIg lambda", {"sIg_dim": "neg"}),
    ("Clonal B-cell count 3.9 x10^9/L", {"lymphocytosis": "neg"}),
    ("Clonal B-cell count 34.2 x10^9/L", {"lymphocytosis": "pos"}),
    ("CD5-positive, CD23-negative B-cell population", {"CD5": "pos", "CD23": "neg"}),
    ("CD5- CD10- CD23-", {"CD5": "neg", "CD10": "neg", "CD23": "neg"}),
    ("MCL is typically CD23 negative", {"CD23": "neg"}),
    ("CD5+ CLL", {"CD5": "pos"}),
    ("Flow shows CD5+, CD23+ and cyclin D1 positive.", {"CD5": "pos", "CD23": "pos", "cyclin_D1": "pos"}),
    ("CD5 and CD23 are both positive", {"CD5": "pos", "CD23": "pos"}),
    ("No splenomegaly or lymphadenopathy.", {"splenomegaly": "neg", "lymphadenopathy": "neg"}),
    ("Smudge cells are frequent.", {"smudge_cells": "pos"}),
    ("t(11;14)(q13;q32) CCND1::IGH detected by FISH.", {"t_11_14": "pos"}),
    ("FISH for CCND1 rearrangement was negative", {"t_11_14": "neg"}),
    ("Monocytes 0.08 x10^9/L", {"monocytopenia": "pos"}),
    ("Ki-67 approximately 45%", {"Ki67_high": "pos"}),
    ("Prolymphocytes are not increased (<5%).", {"prolymphocytes_increased": "neg"}),
    ("CD5-/CD23+", {"CD5": "neg", "CD23": "pos"}),
    ("Serum electrophoresis: no paraprotein detected.", {"IgM_paraprotein": "neg"}),
    ("The cells lack CD5, CD10 and CD23.", {"CD5": "neg", "CD10": "neg", "CD23": "neg"}),
    ("TP53 mutation not detected. No del(17p) detected by FISH.", {"TP53_mut": "neg", "del_17p": "neg"}),
    ("MYD88 L265P not detected (MYD88 wild-type).", {"MYD88_L265P": "neg"}),
    ("No CD5 but CD23 positive", {"CD5": "neg", "CD23": "pos"}),
    ("CD20 bright, CD22+", {"CD20_dim": "neg", "CD22": "pos"}),
    ("Referring clinician's working diagnosis: monoclonal B-cell lymphocytosis.", {}),
    ("CD5 positivity and CD23 negativity", {"CD5": "pos", "CD23": "neg"}),
    ("absence of CD10", {"CD10": "neg"}),
    ("del(17p) detected by FISH (TP53 locus).", {"del_17p": "pos"}),
]


@pytest.mark.parametrize("text,expected", TABLE)
def test_grammar_table(lx, text, expected):
    got = {a.finding_id: a.polarity for a in extract.extract_assertions(text, lx) if a.polarity}
    assert got == expected


def test_mentions_without_polarity_are_not_assertions(lx):
    asserts = extract.extract_assertions("Is cyclin D1 relevant? We should check CD23.", lx)
    assert all(a.polarity is None for a in asserts if a.finding_id in ("CD23",))


def test_bare_minus_only_negative_when_followed_by_boundary(lx):
    got = {a.finding_id: a.polarity for a in extract.extract_assertions("CD5-CD23 double staining", lx)}
    assert got.get("CD5") is None


def test_conflict_flagging_and_findings_raises(lx):
    asserts = extract.extract_assertions("CD5 positive and CD5 negative.", lx)
    assert all("CONFLICT" in a.warnings for a in asserts if a.finding_id == "CD5")
    with pytest.raises(extract.PolarityConflict):
        extract.findings("CD5 positive. CD5 negative.", lx)


def test_spans_index_original_text(lx):
    text = "Flow: CD5+, cyclin D1 negative."
    for a in extract.extract_assertions(text, lx):
        assert text[a.start:a.end].lower() in {al.lower() for al in lx.aliases(a.finding_id)} or a.rule in ("phrase", "numeric")
        assert a.surface == text[min(a.start, a.cue_start):max(a.end, a.cue_end)]


def test_disambiguation(lx):
    assert extract.findings("FISH: BCL2 rearrangement detected.", lx) == {"t_14_18_BCL2": "pos"}
    assert extract.findings("BCL2 expression positive by IHC.", lx) == {"BCL2": "pos"}
    assert extract.findings("FISH: t(14;18) IGH::MALT1 detected.", lx) == {"t_14_18_MALT1": "pos"}
    assert extract.findings("CCND1 rearrangement detected by FISH.", lx) == {"t_11_14": "pos"}


def test_every_sample_case_truth_recovered(sample_cases, lx):
    for c in sample_cases:
        assert extract.findings(c.render(), lx) == c.truth, c.case_id


def test_finding_spans_point_into_reports(sample_cases, lx):
    c = sample_cases[0]
    spans = extract.finding_spans(c, lx)
    assert set(spans) == set(c.truth)
    for fid, lst in spans.items():
        for sp in lst:
            body = c.reports[sp["report"]]
            assert sp["end"] <= len(body)
            assert sp["polarity"] == c.truth[fid]


def test_pilot_list_suffix_distribution(lx):
    """Pilot 2026-10-20: a polarity word after the last member of a list scopes over the unresolved members before it."""
    def pols(text):
        return [(a.finding_id, a.polarity) for a in extract.extract_assertions(text, lx)]
    assert pols("CD11c/CD25/CD103/CD123 positivity with monocytopenia") == [("CD11c", "pos"), ("CD25", "pos"), ("CD103", "pos"), ("CD123", "pos"), ("monocytopenia", "pos")]
    assert pols("CD23 and CD200 negativity are atypical") == [("CD23", "neg"), ("CD200", "neg")]
    assert pols("CD5/CD10/CD23 negativity, splenomegaly")[:3] == [("CD5", "neg"), ("CD10", "neg"), ("CD23", "neg")]
    # explicit suffixes are kept; a run is reset by an explicit symbol and by "with"
    assert pols("CD5+, CD23-, CD200 negative, CD10 and CD103 positive, FMC7") == [("CD5", "pos"), ("CD23", "neg"), ("CD200", "neg"), ("CD10", "pos"), ("CD103", "pos"), ("FMC7", None)]
    assert pols("MYD88 L265P with CD5/CD10/CD23 negativity")[0] == ("MYD88_L265P", None)
    # the word scopes over markers of the same kind only; phrase-join across kinds is off too
    assert pols("only 3% prolymphocytes and CD38 positivity")[0][1] != "pos" and pols("only 3% prolymphocytes and CD38 positivity")[1] == ("CD38", "pos")
    assert pols("cyclin D1 and t(11;14) negative, del13q with mutated IGHV")[:3] == [("cyclin_D1", "neg"), ("t_11_14", "neg"), ("del_13q", None)]
    assert pols("no cyclin D1 or t(11;14), del13q, and mutated IGHV") == [("cyclin_D1", "neg"), ("t_11_14", "neg"), ("del_13q", None), ("IGHV_unmutated", "neg")]
    assert pols("no cyclin D1 or t(11;14), plus del13q and smudge cells on smear") == [("cyclin_D1", "neg"), ("t_11_14", "neg"), ("del_13q", None), ("smudge_cells", "pos")]
    assert pols("negative for CD5, CD10 or CD23") == [("CD5", "neg"), ("CD10", "neg"), ("CD23", "neg")]
    assert pols("Dutcher bodies, MYD88 L265P, and CD5/CD10/CD23-negative immunophenotype")[1:] == [("MYD88_L265P", None), ("CD5", "neg"), ("CD10", "neg"), ("CD23", "neg")]
    assert pols("wild-type MYD88, splenomegaly, marked lymphocytosis") == [("MYD88_L265P", "neg"), ("splenomegaly", "pos"), ("lymphocytosis", "pos")]
    assert pols("negative CD25, wild-type BRAF, weak cyclin D1")[1] == ("BRAF_V600E", "neg")  # "weak cyclin D1" alone stays open (no list cue)
    assert pols("negative CD79b and FMC7, LEF1+, cyclin D1 and t(11;14) negative, del13q with mutated IGHV")[:5] == \
        [("CD79b", "neg"), ("FMC7", "neg"), ("LEF1", "pos"), ("cyclin_D1", "neg"), ("t_11_14", "neg")]
    assert pols("negative CD79b and FMC7, LEF1+, cyclin D1 and t(11;14) negative, del13q with mutated IGHV")[5][1] is None
    # bare minus before a dash; lexicon additions from model prose
    assert pols("LEF1+, cyclin D1-—plus 3% prolymphocytes")[:2] == [("LEF1", "pos"), ("cyclin_D1", "neg")]
    assert pols("sole del13q, mutated IGHV, wild-type TP53") == [("del_13q", "pos"), ("IGHV_unmutated", "neg"), ("TP53_mut", "neg")]
    assert pols("IGHV is unmutated and the case is TP53-mutated; BRAF V600E wasn't detected") == [("IGHV_unmutated", "pos"), ("TP53_mut", "pos"), ("BRAF_V600E", "neg")]
