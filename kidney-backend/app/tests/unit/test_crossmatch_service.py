# app/tests/unit/test_crossmatch_service.py
from app.services.crossmatch_service import check_crossmatch


def test_negative_crossmatch_proceeds():
    result = check_crossmatch(is_positive=False, t_cell_result="Negative", b_cell_result="Negative")

    assert result.is_halted is False
    assert result.is_positive is False


def test_positive_crossmatch_halts():
    result = check_crossmatch(is_positive=True, t_cell_result="Positive", b_cell_result="Negative")

    assert result.is_halted is True
    assert result.is_positive is True


def test_optional_fields_default_to_none():
    result = check_crossmatch(is_positive=False)

    assert result.t_cell_result is None
    assert result.b_cell_result is None
    assert result.remarks is None
