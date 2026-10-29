import math

import pytest

from traceaudit import stats


def test_wilson_known_values():
    lo, hi = stats.wilson(7, 10)
    assert round(lo, 3) == 0.397 and round(hi, 3) == 0.892
    assert stats.wilson(0, 10)[0] == pytest.approx(0.0, abs=1e-12) and stats.wilson(10, 10)[1] == pytest.approx(1.0, abs=1e-12)
    assert all(math.isnan(x) for x in stats.wilson(0, 0))


def test_cluster_bootstrap_reproducible_and_covers():
    recs = [(f"c{i % 10}", 1 if i % 4 == 0 else 0) for i in range(200)]
    stat = lambda rs: sum(r[1] for r in rs) / len(rs)  # noqa: E731
    a = stats.cluster_bootstrap(recs, lambda r: r[0], stat, B=300, seed=1)
    b = stats.cluster_bootstrap(recs, lambda r: r[0], stat, B=300, seed=1)
    assert a == b and a["n_clusters"] == 10 and a["lo"] <= a["point"] <= a["hi"]
    assert stats.cluster_bootstrap([], lambda r: r, stat)["n_clusters"] == 0


def test_rate_ci_fallbacks():
    few = stats.rate_ci([("c1", 1, 1), ("c2", 0, 1), ("c3", 1, 1)], B=50)
    assert few["ci_method"] == "wilson" and few["point"] == round(2 / 3, 4)
    none = stats.rate_ci([], B=10)
    assert none["point"] is None
    many = stats.rate_ci([(f"c{i % 8}", i % 2, 1) for i in range(80)], B=200)
    assert many["ci_method"] == "bootstrap" and many["lo"] <= 0.5 <= many["hi"]


def test_paired_difference():
    a = [(f"c{i}", 1 if i % 2 else 0, 1) for i in range(40)]
    b = [(f"c{i}", 1 if i % 4 == 0 else 0, 1) for i in range(40)]
    d = stats.paired_difference(a, b, B=200)
    assert round(d["point"], 2) == 0.25 and d["lo"] <= d["point"] <= d["hi"]


def test_weighted_kappa_hand_computed():
    a = [1, 2, 3, 4, 2, 3, 1, 4, 3, 2]
    b = [1, 2, 3, 3, 2, 4, 1, 4, 3, 2]
    assert round(stats.weighted_kappa(a, b), 4) == 0.8246
    assert stats.weighted_kappa(a, a) == 1.0
    assert math.isnan(stats.weighted_kappa([], []))
    assert stats.weighted_kappa([1, 1, 2, 2], [2, 2, 1, 1], k=2) < 0


def test_gwet_ac2():
    a = [1, 2, 3, 4, 2, 3, 1, 4, 3, 2]
    b = [1, 2, 3, 3, 2, 4, 1, 4, 3, 2]
    assert round(stats.gwet_ac2([[x, y] for x, y in zip(a, b)]), 4) == 0.8429
    assert stats.gwet_ac2([[1, 1, None], [2, 2, 2]]) > 0.9
    assert math.isnan(stats.gwet_ac2([[1], [2]]))


def test_percent_agreement():
    assert stats.percent_agreement([1, 2, 3], [1, 3, 3]) == pytest.approx(2 / 3)
    assert stats.percent_agreement([1, 2, 3], [1, 3, 3], within=1) == 1.0


def test_agreement_report_shape():
    ratings = []
    for i in range(12):
        for r in ("R01", "R02"):
            for d in ("D1", "D2"):
                ratings.append({"study_id": "s", "rater_id": r, "trace_key": f"k{i}", "dimension": d, "score": 1 + (i + (1 if r == "R02" and i % 3 == 0 else 0)) % 4})
            ratings.append({"study_id": "s", "rater_id": r, "trace_key": f"k{i}", "dimension": "tags", "score": None, "error_tags": ["none"] if i % 2 else ["overconfidence"]})
    judge = [{"trace_key": f"k{i}", "scores": {"D1": 1 + i % 4, "D2": 2}} for i in range(12)]
    rep = stats.agreement_report(ratings, judge, dims=("D1", "D2"), B=50)
    d1 = rep["dimensions"]["D1"]
    assert "R01|R02" in d1["pairwise_kappa"] and d1["gwet_ac2"]["point"] is not None
    assert d1["judge_kappa"]["consensus"]["point"] > 0.5
    assert rep["tags"]["overconfidence"]["R01|R02"] == 1.0


def test_summary_and_long_export(demo_run):
    import csv
    import json
    s = json.loads((demo_run / "summary.json").read_text())
    for key in ("counts", "grounding", "counterfactual", "authority", "knowledge", "effort_contrasts"):
        assert key in s
    assert s["grounding"]["pooled_rate"]["point"] is not None
    assert set(s["counterfactual"]["decisive"]["rule_sensitivity"]) == {"D1", "D2", "D3"}
    assert s["counterfactual"]["decisive"]["silent_rate"]["by_effort"].keys() >= {"low", "medium", "high"}
    rows = list(csv.DictReader(open(demo_run / "long.csv")))
    assert rows and {"trace_key", "kind", "effort", "outcome", "grounding_rate", "disclosed_d1"} <= set(rows[0])
    assert s["judge"] and s["judge"]["n"] > 0


def test_cohen_kappa_hand_computed():
    # 8/10 agree; marginals A 4, B 3, C 3 on both sides -> pe = (16 + 9 + 9) / 100 = 0.34; kappa = (0.8 - 0.34) / 0.66
    a = "A A B B C A B C C A".split()
    b = "A A B C C A B B C A".split()
    assert stats.cohen_kappa(a, b) == pytest.approx(0.46 / 0.66)
    assert stats.cohen_kappa(a, a) == 1.0
    assert math.isnan(stats.cohen_kappa([], []))
    assert math.isnan(stats.cohen_kappa([None, "A"], ["A", None]))
    assert stats.cohen_kappa(["A", "A", "B", "B"], ["B", "B", "A", "A"]) == -1.0
    assert stats.cohen_kappa(a + [None], b + ["A"]) == pytest.approx(0.46 / 0.66)  # None pairs dropped


def test_gwet_ac1():
    # same data as the kappa test: pa = 0.8; pi = A 0.4, B 0.3, C 0.3; pe = (0.24 + 0.21 + 0.21) / (3 - 1) = 0.33
    a = "A A B B C A B C C A".split()
    b = "A A B C C A B B C A".split()
    assert stats.gwet_ac1([[x, y] for x, y in zip(a, b)]) == pytest.approx(0.47 / 0.67)
    # rows [x,x] and [x,y,x]: pa = (1 + 1/3) / 2 = 2/3; pi_x = 5/6, pi_y = 1/6; pe = 2 * 5/36 = 5/18; AC1 = (7/18) / (13/18)
    assert stats.gwet_ac1([["x", "x", None], ["x", "y", "x"]]) == pytest.approx(7 / 13)
    assert math.isnan(stats.gwet_ac1([["x"], ["y"]]))  # every item has fewer than two ratings
    assert stats.gwet_ac1([["x", "x"], ["x", "x"]]) == 1.0
    assert stats.gwet_ac1([["x", "x"], ["x", "y"]], categories=["x", "y", "z"]) > stats.gwet_ac1([["x", "x"], ["x", "y"]])
    with pytest.raises(ValueError):
        stats.gwet_ac1([["x", "q"]], categories=["x", "y"])


def test_per_class_pr():
    pred = "A A B B C A B C C A".split()
    truth = "A A B C C A B B C A".split()
    pr = stats.per_class_pr(pred, truth, ["A", "B", "C", "D"])
    assert pr["A"] == {"tp": 4, "fp": 0, "fn": 0, "support": 4, "predicted": 4, "precision": 1.0, "recall": 1.0}
    assert pr["B"]["precision"] == pytest.approx(2 / 3) and pr["B"]["recall"] == pytest.approx(2 / 3)
    assert pr["D"]["precision"] is None and pr["D"]["recall"] is None and pr["D"]["support"] == 0
