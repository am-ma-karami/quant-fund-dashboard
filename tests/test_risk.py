from pytest import approx

from services.risk import (
    returns_from_prices,
    annualized_volatility,
    sharpe_ratio,
    maximum_drawdown,
)


def test_returns():
    result = returns_from_prices(
        [100, 110]
    )

    assert result == approx([0.1])


def test_max_drawdown():
    result = maximum_drawdown(
        [100, 120, 90]
    )

    assert round(result, 4) == -0.25


def test_volatility():
    returns = [0.01, -0.01, 0.02]

    result = annualized_volatility(returns)

    assert result is not None


def test_sharpe():
    returns = [0.01, 0.02, 0.015]

    result = sharpe_ratio(returns)

    assert result is not None
