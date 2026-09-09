import pytest

from services.history_bootstrap import parse_tsetmc_date


def test_parse_tsetmc_date_valid():
    result = parse_tsetmc_date(20260908)

    assert result is not None
    assert result.year == 2026
    assert result.month == 9
    assert result.day == 8


def test_parse_tsetmc_date_invalid_string():
    assert parse_tsetmc_date("invalid") is None


def test_parse_tsetmc_date_invalid_number():
    assert parse_tsetmc_date(20261399) is None


def test_parse_tsetmc_date_none():
    assert parse_tsetmc_date(None) is None


def test_parse_tsetmc_date_short():
    assert parse_tsetmc_date(202609) is None
