from pathlib import Path

import pytest

from traceaudit import lexicon as lex_mod
from traceaudit.schema import load_cases, load_perturbations

PKG = Path(__file__).resolve().parents[1] / "traceaudit"


@pytest.fixture(scope="session")
def lx():
    return lex_mod.load()


@pytest.fixture(scope="session")
def sample_cases():
    return load_cases(PKG / "domains" / "haematology" / "sample_cases.jsonl")


@pytest.fixture(scope="session")
def sample_perts():
    return load_perturbations(PKG / "domains" / "haematology" / "sample_perturbations.jsonl")


@pytest.fixture(scope="session")
def by_case(sample_cases):
    return {c.case_id: c for c in sample_cases}


@pytest.fixture(scope="session")
def demo_run(tmp_path_factory):
    """A small SimulatedModel run, scored, shared across tests."""
    from traceaudit.cli import main
    out = tmp_path_factory.mktemp("demo") / "run"
    rc = main(["demo", "--out", str(out), "--runs", "2", "--B", "100", "--judge"])
    assert rc == 0
    return out


def pytest_addoption(parser):
    parser.addoption("--update-golden", action="store_true", help="rewrite tests/golden/*.json")
    parser.addoption("--slow", action="store_true", help="run slow tests")


def pytest_configure(config):
    config.addinivalue_line("markers", "slow: slow end-to-end validation")


def pytest_collection_modifyitems(config, items):
    if config.getoption("--slow"):
        return
    skip = pytest.mark.skip(reason="pass --slow")
    for item in items:
        if "slow" in item.keywords:
            item.add_marker(skip)
