import json

import pytest

from traceaudit.validation import GRIDS, run_grid


@pytest.mark.slow
def test_quick_grid_passes(tmp_path):
    res = run_grid("quick", tmp_path, 20261020)
    assert res["passed"], json.dumps([r for r in res["results"] if not r["passed"]], indent=1)[:3000]


def test_grids_defined():
    assert set(GRIDS["quick"]) <= set(GRIDS["default"]) | {"mid", "silent_only", "authority_only", "clean"}
