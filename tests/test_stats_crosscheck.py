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
