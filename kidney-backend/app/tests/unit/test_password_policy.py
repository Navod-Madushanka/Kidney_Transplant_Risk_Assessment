# app/tests/unit/test_password_policy.py
from app.scripts.password_policy import MIN_PASSWORD_LENGTH, validate_password_strength


def test_strong_password_has_no_problems():
    assert validate_password_strength("correct-horse-battery-staple-42") == []


def test_too_short_is_rejected():
    problems = validate_password_strength("Short1!")
    assert any("12 characters" in p for p in problems)


def test_one_character_under_minimum_length_is_rejected_for_length():
    problems = validate_password_strength("x" * (MIN_PASSWORD_LENGTH - 1))
    assert any("characters long" in p for p in problems)


def test_exactly_minimum_length_is_not_rejected_for_length():
    # Still rejected for being a repeated character -- this only checks
    # that the *length* problem specifically doesn't fire once the string
    # is long enough.
    problems = validate_password_strength("x" * MIN_PASSWORD_LENGTH)
    assert not any("characters long" in p for p in problems)


def test_exact_common_password_is_rejected():
    problems = validate_password_strength("password123")
    assert any("common passwords" in p for p in problems)


def test_common_password_check_is_case_insensitive():
    problems = validate_password_strength("PASSWORD123")
    assert any("common passwords" in p for p in problems)


def test_password_containing_a_common_password_as_a_substring_is_rejected():
    # Not an exact match against the common-password list, but still an
    # obviously guessable pattern (a dictionary word plus a suffix).
    problems = validate_password_strength("password123456")
    assert any("easily-guessed word" in p for p in problems)


def test_guessable_substring_is_rejected():
    problems = validate_password_strength("MyHospital2026Login")
    assert any("hospital" in p for p in problems)


def test_near_single_character_is_rejected():
    problems = validate_password_strength("aaaaaaaaaaaaaaaa")
    assert any("repeated character" in p for p in problems)


def test_sequential_digits_are_rejected():
    # Digits 0-9 are all there are, so a strictly-ascending, non-repeating
    # run tops out at 10 characters -- shorter than MIN_PASSWORD_LENGTH,
    # so this also (correctly) trips the length check alongside it.
    problems = validate_password_strength("0123456789")
    assert any("sequential run of digits" in p for p in problems)


def test_descending_sequential_digits_are_rejected():
    problems = validate_password_strength("9876543210")
    assert any("sequential run of digits" in p for p in problems)
