from fecreator.assets.portrait.review import ReviewThresholds, review_gate
from fecreator.contracts.diagnostics import has_errors


def test_passing_metrics_no_error() -> None:
    metrics = {
        "identity": 0.95,
        "silhouette": 0.97,
        "protected_diff": 0.0,
        "palette_distance": 3.0,
    }
    assert review_gate(metrics) == []


def test_low_identity_fails() -> None:
    metrics = {
        "identity": 0.5,
        "silhouette": 0.97,
        "protected_diff": 0.0,
        "palette_distance": 3.0,
    }
    diags = review_gate(metrics)
    assert has_errors(diags)
    assert any(d.code == "IDENTITY_BELOW_THRESHOLD" for d in diags)


def test_missing_metric_fails_closed() -> None:
    assert has_errors(review_gate({}))


def test_custom_thresholds() -> None:
    metrics = {
        "identity": 0.80,
        "silhouette": 0.95,
        "protected_diff": 0.0,
        "palette_distance": 1.0,
    }
    assert review_gate(metrics, ReviewThresholds(identity_min=0.75)) == []


# ---------------------------------------------------------------------------
# NEW: NaN / inf must fail closed
# ---------------------------------------------------------------------------


def test_nan_identity_fails_closed() -> None:
    metrics = {
        "identity": float("nan"),
        "silhouette": 0.97,
        "protected_diff": 0.0,
        "palette_distance": 3.0,
    }
    diags = review_gate(metrics)
    assert has_errors(diags)
    assert any(d.code == "IDENTITY_BELOW_THRESHOLD" for d in diags)


def test_pos_inf_identity_fails_closed() -> None:
    """+inf identity looks perfect but is non-finite → must fail closed."""
    metrics = {
        "identity": float("inf"),
        "silhouette": 0.97,
        "protected_diff": 0.0,
        "palette_distance": 3.0,
    }
    assert has_errors(review_gate(metrics))


def test_nan_silhouette_fails_closed() -> None:
    metrics = {
        "identity": 0.95,
        "silhouette": float("nan"),
        "protected_diff": 0.0,
        "palette_distance": 3.0,
    }
    diags = review_gate(metrics)
    assert has_errors(diags)
    assert any(d.code == "SILHOUETTE_BELOW_THRESHOLD" for d in diags)


def test_neg_inf_silhouette_fails_closed() -> None:
    metrics = {
        "identity": 0.95,
        "silhouette": float("-inf"),
        "protected_diff": 0.0,
        "palette_distance": 3.0,
    }
    assert has_errors(review_gate(metrics))


def test_nan_protected_diff_fails_closed() -> None:
    metrics = {
        "identity": 0.95,
        "silhouette": 0.97,
        "protected_diff": float("nan"),
        "palette_distance": 3.0,
    }
    diags = review_gate(metrics)
    assert has_errors(diags)
    assert any(d.code == "PROTECTED_DIFF_TOO_HIGH" for d in diags)


def test_nan_palette_distance_fails_closed() -> None:
    metrics = {
        "identity": 0.95,
        "silhouette": 0.97,
        "protected_diff": 0.0,
        "palette_distance": float("nan"),
    }
    diags = review_gate(metrics)
    assert has_errors(diags)
    assert any(d.code == "PALETTE_DISTANCE_TOO_HIGH" for d in diags)


def test_all_nan_fails_closed() -> None:
    nan_metrics = {
        k: float("nan") for k in ["identity", "silhouette", "protected_diff", "palette_distance"]
    }
    diags = review_gate(nan_metrics)
    assert has_errors(diags)
    assert len(diags) == 4  # all four metrics triggered
