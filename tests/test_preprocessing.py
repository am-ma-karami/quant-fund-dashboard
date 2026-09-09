import pytest

from services.preprocessing import clean_fund_data, validate_percentage


def test_clean_fund_data_valid():
    raw_data = {
        "regNo": "12345",
        "navStat": 150000.5,
        "mfName": " صندوق تست ",
        "portfolioStock": 45.5,
        "day30Return": 2.5
    }

    cleaned = clean_fund_data(raw_data)

    assert cleaned["reg_no"] == 12345
    assert cleaned["name"] == "صندوق تست"
    assert cleaned["nav_stat"] == 150000.5
    assert cleaned["portfolio_stock"] == 45.5
    assert cleaned["day30_return"] == 2.5


def test_clean_fund_data_preserves_nulls():
    raw_data = {
        "regNo": None,
        "navStat": None,
        "portfolioStock": None,
    }

    cleaned = clean_fund_data(raw_data)

    assert cleaned["reg_no"] == 0
    assert cleaned["nav_stat"] is None
    assert cleaned["portfolio_stock"] is None
    assert cleaned["name"] == "نامشخص"


def test_validate_percentage_rejects_outliers():
    with pytest.raises(ValueError):
        validate_percentage(150, "portfolio_stock")

    with pytest.raises(ValueError):
        validate_percentage(-10, "portfolio_bond")


def test_validate_percentage_accepts_valid():
    assert validate_percentage(45.5, "portfolio_stock") == 45.5
