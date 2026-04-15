import pytest

from sajucandle.handlers import BirthParseError, parse_birth_args


def test_parse_birth_args_valid():
    assert parse_birth_args(["1990-03-15", "14:00"]) == (1990, 3, 15, 14, 0)


def test_parse_birth_args_with_seconds_ignored():
    assert parse_birth_args(["1990-03-15", "14:00:30"]) == (1990, 3, 15, 14, 0)


def test_parse_birth_args_hour_only():
    """시:분 없이 시만 온 경우도 허용 (분 기본 0)."""
    assert parse_birth_args(["1990-03-15", "14"]) == (1990, 3, 15, 14, 0)


def test_parse_birth_args_empty_raises():
    with pytest.raises(BirthParseError):
        parse_birth_args([])


def test_parse_birth_args_missing_time_raises():
    with pytest.raises(BirthParseError):
        parse_birth_args(["1990-03-15"])


def test_parse_birth_args_bad_date_format_raises():
    with pytest.raises(BirthParseError):
        parse_birth_args(["1990/03/15", "14:00"])


def test_parse_birth_args_invalid_hour_raises():
    with pytest.raises(BirthParseError):
        parse_birth_args(["1990-03-15", "25:00"])


def test_parse_birth_args_invalid_month_raises():
    with pytest.raises(BirthParseError):
        parse_birth_args(["1990-13-15", "14:00"])
