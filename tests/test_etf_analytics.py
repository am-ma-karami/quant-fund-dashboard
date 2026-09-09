from pytest import approx

from services.etf_analytics import (
    calculate_premium_discount,
    calculate_premium_zscore,
)


def test_positive_premium():
    result = calculate_premium_discount(
        market_price=110,
        nav=100,
    )

    assert result == approx(10.0)


def test_negative_discount():
    result = calculate_premium_discount(
        market_price=90,
        nav=100,
    )

    assert result == approx(-10.0)


def test_invalid_nav():
    assert calculate_premium_discount(100, 0) is None


def test_missing_price():
    assert calculate_premium_discount(None, 100) is None


def test_premium_zscore():
    score = calculate_premium_zscore(
        12,
        [8, 9, 10, 11],
    )

    assert score is not None
    assert score > 0


def test_premium_zscore_insufficient():
    assert calculate_premium_zscore(12, [8]) is None
