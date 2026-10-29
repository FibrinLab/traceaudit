"""Cross-check stdlib statistics against SciPy / statsmodels / scikit-learn (requires the [stats] extra)."""
import random

import pytest

from traceaudit import stats

sk = pytest.importorskip("sklearn.metrics")
sm = pytest.importorskip("statsmodels.stats.proportion")


def test_weighted_kappa_matches_sklearn():
    rng = random.Random(1)
    for _ in range(20):
        a = [rng.randint(1, 4) for _ in range(60)]
        b = [x if rng.random() < 0.7 else rng.randint(1, 4) for x in a]
        for w in ("linear", "quadratic"):
            assert stats.weighted_kappa(a, b, weights=w) == pytest.approx(sk.cohen_kappa_score(a, b, weights=w), abs=1e-9)


def test_wilson_matches_statsmodels():
    for k, n in ((0, 10), (3, 10), (7, 10), (10, 10), (50, 200)):
        lo, hi = sm.proportion_confint(k, n, method="wilson")
        assert stats.wilson(k, n) == pytest.approx((lo, hi), abs=1e-6)


def test_cohen_kappa_matches_sklearn():
    rng = random.Random(2)
    labels = ["agree", "disagree", "unverifiable", "not_mentioned"]
    for _ in range(20):
        a = [rng.choice(labels) for _ in range(80)]
        b = [x if rng.random() < 0.6 else rng.choice(labels) for x in a]
        assert stats.cohen_kappa(a, b) == pytest.approx(sk.cohen_kappa_score(a, b), abs=1e-9)


def test_per_class_pr_matches_sklearn():
    rng = random.Random(3)
    labels = ["agree", "disagree", "unverifiable", "not_mentioned"]
    for _ in range(10):
        truth = [rng.choice(labels) for _ in range(80)]
        pred = [x if rng.random() < 0.6 else rng.choice(labels) for x in truth]
        p, r, _, s = sk.precision_recall_fscore_support(truth, pred, labels=labels, zero_division=0)
        mine = stats.per_class_pr(pred, truth, labels)
        for i, c in enumerate(labels):
            assert mine[c]["support"] == s[i]
            if mine[c]["precision"] is not None:
                assert mine[c]["precision"] == pytest.approx(p[i], abs=1e-9)
            if mine[c]["recall"] is not None:
                assert mine[c]["recall"] == pytest.approx(r[i], abs=1e-9)
