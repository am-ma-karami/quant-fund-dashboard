import pytest

from services.preprocessing import clean_fund_data, normalize_fund_name


def test_clean_fund_data_scales_portfolio_to_100():
    raw_data = {
        "regNo": "12345",
        "navStat": 150000.5,
        "mfName": " صندوق تست ",
        "portfolioStock": 45.5,
        "portfolioBond": 30.0,
        "portfolioCash": 15.0,
        "portfolioOther": 9.5,
        "day30Return": 2.5,
    }

    cleaned = clean_fund_data(raw_data)

    assert cleaned["reg_no"] == 12345
    assert cleaned["name"] == "صندوق تست"
    assert cleaned["nav_stat"] == 150000.5
    assert cleaned["portfolio_stock"] == 45.5
    assert cleaned["portfolio_bond"] == 30.0
    assert cleaned["portfolio_cash"] == 15.0
    assert cleaned["portfolio_other"] == 9.5
    assert cleaned["day30_return"] == 2.5


def test_clean_fund_data_uses_max_cash_deposit():
    raw_data = {
        "regNo": "12345",
        "navStat": 1000.0,
        "mfName": "تست",
        "portfolioStock": 50.0,
        "portfolioBond": 30.0,
        "portfolioCash": 10.0,
        "portfolioDeposit": 20.0,
        "portfolioOther": 0.0,
    }

    cleaned = clean_fund_data(raw_data)

    assert cleaned["portfolio_cash"] == 20.0
    assert cleaned["portfolio_stock"] == 50.0
    assert cleaned["portfolio_bond"] == 30.0
    assert cleaned["portfolio_other"] == 0.0


def test_clean_fund_data_null_inputs_become_zero():
    raw_data = {
        "regNo": None,
        "navStat": None,
        "portfolioStock": None,
    }

    cleaned = clean_fund_data(raw_data)

    assert cleaned["reg_no"] == 0
    assert cleaned["nav_stat"] == 0.0
    assert cleaned["portfolio_stock"] == 0.0
    assert cleaned["name"] == "نامشخص"


def test_normalize_fund_name_removes_keywords():
    assert normalize_fund_name("صندوق سرمایه گذاری در سهام یاقوت") == "یاقوت"
    assert normalize_fund_name("صندوقETFاختصاصی طلا") == "طلا"


def test_normalize_fund_name_preserves_core():
    assert normalize_fund_name("صندوق مشترک عیار") == "عیار"
