# app/tests/unit/test_pra_bucket_service.py
from app.services.cpra_service import CPRAResult
from app.services.pra_bucket_service import calculate_pra_bucket


def _cpra(percentage, sufficient=True):
    return CPRAResult(
        cpra_percentage=percentage,
        sample_size=150,
        has_sufficient_data=sufficient,
        message="OK",
    )


def test_insufficient_data_does_not_halt_and_has_no_bucket():
    result = calculate_pra_bucket(_cpra(None, sufficient=False))

    assert result.has_sufficient_data is False
    assert result.bucket_name is None
    assert result.is_halted is False


def test_below_30_percent_buckets_low_and_proceeds():
    result = calculate_pra_bucket(_cpra(15.0))

    assert result.bucket_name == "<30%"
    assert result.is_halted is False


def test_29_point_9_still_buckets_below_30():
    result = calculate_pra_bucket(_cpra(29.9))

    assert result.bucket_name == "<30%"
    assert result.is_halted is False


def test_30_to_60_percent_buckets_mid_and_proceeds():
    result = calculate_pra_bucket(_cpra(45.0))

    assert result.bucket_name == "30-60%"
    assert result.is_halted is False


def test_exactly_60_percent_does_not_halt():
    # 60.0 is the reject threshold's boundary — "> 60" rejects, so exactly
    # 60 must still proceed.
    result = calculate_pra_bucket(_cpra(60.0))

    assert result.bucket_name == "30-60%"
    assert result.is_halted is False


def test_above_60_percent_halts():
    result = calculate_pra_bucket(_cpra(60.5))

    assert result.bucket_name == ">60%"
    assert result.is_halted is True


def test_high_pra_halts():
    result = calculate_pra_bucket(_cpra(95.0))

    assert result.bucket_name == ">60%"
    assert result.is_halted is True
