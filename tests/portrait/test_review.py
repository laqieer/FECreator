from fecreator.assets.portrait.review import ReviewThresholds, review_gate
from fecreator.contracts.diagnostics import has_errors


def test_passing_metrics_no_error():
    metrics = {
        "identity": 0.95,
        "silhouette": 0.97,
        "protected_diff": 0.0,
        "palette_distance": 3.0,
    }
    assert review_gate(metrics) == []


def test_low_identity_fails():
    metrics = {
        "identity": 0.5,
        "silhouette": 0.97,
        "protected_diff": 0.0,
        "palette_distance": 3.0,
    }
    diags = review_gate(metrics)
    assert has_errors(diags)
    assert any(d.code == "IDENTITY_BELOW_THRESHOLD" for d in diags)


def test_missing_metric_fails_closed():
    assert has_errors(review_gate({}))


def test_custom_thresholds():
    metrics = {
        "identity": 0.80,
        "silhouette": 0.95,
        "protected_diff": 0.0,
        "palette_distance": 1.0,
    }
    assert review_gate(metrics, ReviewThresholds(identity_min=0.75)) == []
