# app/tests/unit/test_pra_bucket_service.py
"""Coverage for calculate_pra_bucket()'s bucketing math and its is_halted
flag. is_halted is informational only (whether cPRA exceeds the >60%
clinical threshold) — match_pipeline.py never branches on it to reject a
pairing; see pra_bucket_service.py's module docstring for why cPRA can't be
a pair-specific reject gate."""
from app.services.cpra_service import CPRAResult
from app.services.pra_bucket_service import calculate_pra_bucket


def _cpra(percentage, sufficient=True):
    return CPRAResult(
        cpra_percentage=percentage,
        sample_size=150,
        has_sufficient_data=sufficient,
        message="OK",
        reference_table_version="test-v1",
        source_citation="test citation",
    )


def test_insufficient_data_leaves_is_halted_false_and_has_no_bucket():
    result = calculate_pra_bucket(_cpra(None, sufficient=False))

    assert result.has_sufficient_data is False
    assert result.bucket_name is None
    assert result.is_halted is False


def test_below_30_percent_buckets_low():
    result = calculate_pra_bucket(_cpra(15.0))

    assert result.bucket_name == "<30%"
    assert result.is_halted is False


def test_29_point_9_still_buckets_below_30():
    result = calculate_pra_bucket(_cpra(29.9))

    assert result.bucket_name == "<30%"
    assert result.is_halted is False


def test_29_point_9995_no_longer_falls_through_to_the_top_bucket():
    # Review #2 bug 17: the old min<=x<=max loop over (0-29.999, 30-60,
    # 60.001-100) left a real gap here -- 29.9995 matched no bucket and
    # fell through to the *most severe* fallback (">60%"), the wrong
    # direction to fail in.
    result = calculate_pra_bucket(_cpra(29.9995))

    assert result.bucket_name == "<30%"


def test_exactly_30_percent_buckets_mid_not_low():
    result = calculate_pra_bucket(_cpra(30.0))

    assert result.bucket_name == "30-60%"


def test_30_to_60_percent_buckets_mid():
    result = calculate_pra_bucket(_cpra(45.0))

    assert result.bucket_name == "30-60%"
    assert result.is_halted is False


def test_exactly_60_percent_stays_below_the_high_sensitisation_threshold():
    # 60.0 is the threshold's boundary — "> 60" is the high-sensitisation
    # case, so exactly 60 must still bucket as "30-60%".
    result = calculate_pra_bucket(_cpra(60.0))

    assert result.bucket_name == "30-60%"
    assert result.is_halted is False


def test_above_60_percent_sets_is_halted_flag():
    # is_halted here is informational only — match_pipeline.py doesn't act
    # on it. See the module docstring.
    result = calculate_pra_bucket(_cpra(60.5))

    assert result.bucket_name == ">60%"
    assert result.is_halted is True


def test_very_high_pra_also_sets_is_halted_flag():
    result = calculate_pra_bucket(_cpra(95.0))

    assert result.bucket_name == ">60%"
    assert result.is_halted is True
