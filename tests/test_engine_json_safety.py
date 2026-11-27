from app.engine_suite import _sanitize_runtime_value


def test_engine_runtime_suppresses_nan_and_infinity_for_json_safety():
    invalid = []
    value = _sanitize_runtime_value(
        {"nested": [1.0, float("inf"), {"score": float("nan")}]},
        invalid_paths=invalid,
    )
    assert value == {"nested": [1.0, None, {"score": None}]}
    assert invalid == ["$.nested[1]", "$.nested[2].score"]
