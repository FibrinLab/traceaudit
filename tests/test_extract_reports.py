"""Invariants C1/C2 over every case in data/cases.jsonl (if present) and the packaged sample; generated cases across seeds."""
from pathlib import Path

import pytest

from traceaudit import extract, schema
from traceaudit.domains.haematology import casegen

ROOT = Path(__file__).resolve().parents[1]


def _case_files():
    files = [ROOT / "traceaudit" / "domains" / "haematology" / "sample_cases.jsonl"]
    if (ROOT / "data" / "cases.jsonl").exists():
        files.append(ROOT / "data" / "cases.jsonl")
    return files


@pytest.mark.parametrize("path", _case_files(), ids=lambda p: p.name)
def test_c1_c2_all_cases(path, lx):
    for c in schema.load_cases(path):
        probs = [p for p in schema.validate_case(c, lx) if p.severity == "error"]
        assert not probs, [str(p) for p in probs]


@pytest.mark.parametrize("seed", [20261020, 7])
def test_generated_cases_pass_c1(seed, lx):
    priors = casegen.load_priors()
    for ent in casegen.CASE_PREFIX:
        for i in range(1, 6):
            c = casegen.generate_case(ent, i, seed, lx, priors)
            assert extract.findings(c.render(), lx) == c.truth
            assert not [p for p in schema.validate_case(c, lx) if p.severity == "error"]


def test_generated_set_has_discordant_and_incomplete(lx):
    cases = casegen.generate_set(20, 20261020, lx)
    assert len(cases) == 120
    assert sum(c.flags.discordant for c in cases) >= 4
    assert sum(c.flags.incomplete for c in cases) >= 1
    assert all(c.truth for c in cases)
