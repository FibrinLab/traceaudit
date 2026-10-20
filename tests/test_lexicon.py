from traceaudit.lexicon import _alias_regex


def test_alias_uniqueness_and_tables(lx):
    seen = {}
    for f in lx.data["findings"]:
        for a in f["aliases"] + f["pos_phrases"] + f["neg_phrases"]:
            assert a.lower() not in seen or seen[a.lower()] == f["id"], a
            seen[a.lower()] = f["id"]
    for fid in lx.discriminators:
        assert fid in lx.findings
    for fid, links in lx.linked.items():
        assert fid in lx.findings
        assert all(l in lx.findings for l in links)
    for ent, wrong in lx.confusion.items():
        assert ent in lx.entities and all(w in lx.entities for w in wrong)
    for e in lx.data["entities"]:
        assert e["aliases"]


def test_short_uppercase_aliases_are_case_sensitive(lx):
    assert [m.entity for m in lx.find_entities("MCV 90 fL")] == []
    assert [m.entity for m in lx.find_entities("favour FL here")] == ["FL"]
    assert lx.marker_tokens("cd56 and CD56 are not CD5") == [m for m in lx.marker_tokens("cd56 and CD56 are not CD5") if m.finding_id == "CD5"]


def test_flexible_separators_and_fusions(lx):
    toks = {m.finding_id for m in lx.marker_tokens("cyclin-D1, cyclinD1, cyclin D1; IGH::CCND1, CCND1/IGH, CCND1-IGH; FMC-7")}
    assert {"cyclin_D1", "t_11_14", "FMC7"} <= toks


def test_entity_subtypes_map_to_parent(lx):
    assert lx.normalise_entity_full("splenic marginal zone lymphoma") == ("MZL", "SMZL")
    assert lx.normalise_entity_full("Waldenström macroglobulinaemia") == ("LPL", "WM")
    assert lx.normalise_entity("hairy cell leukemia variant") == "SBLPN"
    assert lx.normalise_entity("nothing here") is None


def test_expected_and_phrases(lx):
    assert lx.expected("cyclin_D1", "MCL") == "pos"
    assert lx.expected("CD5", "FL") == "neg"
    assert lx.has_phrase("hedge", "the differential includes MCL")
    assert not lx.has_phrase("hedge", "mantle cell lymphoma")
    assert _alias_regex("t(11;14)").search("karyotype shows t(11;14)(q13;q32)")
