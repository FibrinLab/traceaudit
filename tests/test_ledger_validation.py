import pytest

from traceaudit import validation
from traceaudit.ledger_sim import LedgerSimParams


def test_planted_includes_ledger_metrics():
    p = LedgerSimParams(p_silent=0.3, p_ablation_ignored=0.4, p_contract_break=0.5)
    planted = validation._ledger_planted(p)
    assert planted["load_bearing_rate"] == 0.6 and planted["contract_fallback_share"] == 0.5 and planted["silent_rate"] == pytest.approx(0.3)
    assert set(validation.LEDGER_GRIDS["quick"]) == {"clean", "mid", "silent_only", "authority_only", "ablation_only", "contract_break"}


@pytest.mark.slow
def test_ledger_quick_grid_passes(tmp_path):
    res = validation.run_ledger_grid("quick", tmp_path, 0)
    assert res["passed"], [r["config"] for r in res["results"] if not r["passed"]]
    assert (tmp_path / "validation.md").exists()
